package service

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

func TestAnthropicStreamRecovery_ErrorEventPreservesUsageAndIsolatesModel(t *testing.T) {
	for _, passthrough := range []bool{true, false} {
		for _, kind := range []string{"api_error", "permission_error", "invalid_request_error"} {
			t.Run(kind, func(t *testing.T) {
				svc := &GatewayService{rateLimitService: &RateLimitService{}}
				account := &Account{ID: 1, Platform: PlatformAnthropic, Type: AccountTypeAPIKey, Status: StatusActive, Schedulable: true}
				body := "data: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":11}}}\n\n" +
					"event: error\ndata: {\"type\":\"error\",\"error\":{\"type\":\"" + kind + "\"}}\n\n"
				c, _ := gin.CreateTestContext(httptest.NewRecorder())
				c.Request = httptest.NewRequest(http.MethodPost, "/v1/messages", nil)
				resp := &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(body))}
				var result *streamingResult
				var err error
				if passthrough {
					result, err = svc.handleStreamingResponseAnthropicAPIKeyPassthrough(context.Background(), resp, c, account, time.Now(), "claude-a")
				} else {
					result, err = svc.handleStreamingResponse(context.Background(), resp, c, account, time.Now(), "claude-a", "claude-a", false)
				}
				require.Error(t, err)
				if passthrough {
					require.Equal(t, 11, result.usage.InputTokens)
				}
				require.Equal(t, kind == "invalid_request_error", svc.isAccountSchedulableForModelSelection(context.Background(), account, "claude-a"))
				require.True(t, svc.isAccountSchedulableForModelSelection(context.Background(), account, "claude-b"))
			})
		}
	}
}

func TestAnthropicStreamRecovery_ProbeAndCancellation(t *testing.T) {
	svc := &GatewayService{}
	account := &Account{ID: 1, Platform: PlatformAnthropic, Type: AccountTypeAPIKey, Status: StatusActive, Schedulable: true}
	state := svc.anthropicStreamRecovery()
	state.recordFailureWithInitialCooldown(1, "claude-a", time.Now().Add(-20*time.Second), time.Second, openAITransientFailureOptions{requireProbe: true})
	var releases atomic.Int32
	ctx, cancel := context.WithCancel(context.Background())
	release, complete, ok := svc.admitAnthropicStreamRecoveryModel(ctx, account, "claude-a", func() { releases.Add(1) })
	require.True(t, ok)
	_, _, ok = svc.admitAnthropicStreamRecoveryModel(context.Background(), account, "claude-a", nil)
	require.False(t, ok)
	cancel()
	require.Eventually(t, func() bool { return releases.Load() == 1 }, time.Second, time.Millisecond)
	complete(true)
	release()
	require.Equal(t, int32(1), releases.Load())
	require.Len(t, state.snapshot(time.Now()), 1, "canceled probe cannot restore model")
	release, complete, ok = svc.admitAnthropicStreamRecoveryModel(context.Background(), account, "claude-a", nil)
	require.True(t, ok)
	complete(true)
	release()
	require.Empty(t, state.snapshot(time.Now()))
}
