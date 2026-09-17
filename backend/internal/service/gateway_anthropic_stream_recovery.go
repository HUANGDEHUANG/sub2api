package service

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/Wei-Shaw/sub2api/internal/pkg/logger"
	"github.com/tidwall/gjson"
	"go.uber.org/zap"
)

// Keep stream failures separate from pre-response failover errors: once bytes
// have been sent, another account must never be appended to the same stream.
type anthropicStreamFailure struct {
	reason    string
	transient bool
}

func (e *anthropicStreamFailure) Error() string { return "anthropic stream failed: " + e.reason }

func anthropicStreamError(data string) error {
	if gjson.Get(data, "type").String() != "error" {
		return nil
	}
	return classifyAnthropicStreamError(data)
}

func classifyAnthropicStreamError(data string) error {
	kind := gjson.Get(data, "error.type").String()
	switch kind {
	case "invalid_request_error", "not_found_error", "request_too_large":
		return &anthropicStreamFailure{reason: "request_rejected"}
	default:
		return &anthropicStreamFailure{reason: "upstream_error_event", transient: true}
	}
}

func (s *GatewayService) anthropicStreamRecovery() *openAIAccountModelTransientState {
	s.anthropicStreamTransientOnce.Do(func() {
		s.anthropicStreamTransient = newOpenAIAccountModelTransientState(openAIModelTransientDefaultMax)
	})
	return s.anthropicStreamTransient
}

func anthropicStreamRecoveryAccount(account *Account) bool {
	return account != nil && account.Platform == PlatformAnthropic && account.Type == AccountTypeAPIKey
}

func (s *GatewayService) recordAnthropicStreamFailure(ctx context.Context, account *Account, model string, err error) {
	var failure *anthropicStreamFailure
	if !anthropicStreamRecoveryAccount(account) || ctx.Err() != nil || !errors.As(err, &failure) || !failure.transient {
		return
	}
	d := s.anthropicStreamRecovery().recordFailureWithInitialCooldown(account.ID, model, time.Now(), openAIModelTransientShortCooldown,
		openAITransientFailureOptions{requireProbe: true, reason: "anthropic_" + failure.reason})
	if d.Cooldown > 0 {
		logger.FromContext(ctx).Warn("gateway.anthropic_model_stream_cooldown", zap.Int64("account_id", account.ID),
			zap.String("model", model), zap.String("reason", failure.reason), zap.Duration("cooldown", d.Cooldown))
	}
}

// Both forward paths check admission after mapping. Cancellation releases probes.
func (s *GatewayService) admitAnthropicStreamRecoveryModel(ctx context.Context, account *Account, model string, release func()) (func(), func(bool), bool) {
	if !anthropicStreamRecoveryAccount(account) {
		return release, func(bool) {}, true
	}
	state := s.anthropicStreamRecovery()
	blocked, id := state.reserveProbe(account.ID, model, time.Now())
	if blocked {
		if release != nil {
			release()
		}
		return nil, nil, false
	}
	var once sync.Once
	wrapped := func() {
		once.Do(func() {
			state.releaseProbe(account.ID, model, id)
			if release != nil {
				release()
			}
		})
	}
	stop := context.AfterFunc(ctx, wrapped)
	return func() { stop(); wrapped() }, func(success bool) {
		if success && ctx.Err() == nil {
			state.completeProbe(account.ID, model, id, time.Now())
		}
	}, true
}

func incompleteAnthropicStream(reason string) error {
	return &anthropicStreamFailure{reason: "stream " + reason, transient: true}
}
