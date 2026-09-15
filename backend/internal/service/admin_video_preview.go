package service

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

// Historical completed tasks are previewable without a separately captured URL.
// Enforce retention on every read as well as in the cleanup job.
func ListAdminVideoPreviewURLs(log *UsageLog, now time.Time) []string {
	if log == nil || log.VideoCount <= 0 || log.CreatedAt.IsZero() ||
		!log.CreatedAt.After(now.Add(-adminVideoPreviewRetention)) || log.CreatedAt.After(now) {
		return nil
	}
	if _, err := adminVideoTaskID(log.RequestID); err != nil {
		return nil
	}
	return []string{fmt.Sprintf("/api/v1/admin/usage/%d/videos/0", log.ID)}
}

func adminVideoTaskID(requestID string) (string, error) {
	// Billing uses an idempotency prefix which is not part of the upstream ID.
	taskID := strings.TrimPrefix(strings.TrimSpace(requestID), "grok-video:")
	if err := validateUpstreamPathSegment("video task id", taskID); err != nil {
		return "", err
	}
	return taskID, nil
}

func (s *OpenAIGatewayService) adminVideoContentURL(account *Account, requestID string) (string, error) {
	taskID, err := adminVideoTaskID(requestID)
	if err != nil {
		return "", err
	}
	if account == nil {
		return "", fmt.Errorf("unsupported video account")
	}
	if account.IsGrok() {
		return buildGrokMediaURL(account, s.cfg, GrokMediaEndpointVideoContent, taskID)
	}
	if !account.IsOpenAIApiKey() {
		return "", fmt.Errorf("unsupported video account")
	}
	base, err := s.validateUpstreamBaseURL(account.GetOpenAIBaseURL())
	if err != nil {
		return "", err
	}
	target, err := url.Parse(buildOpenAIEndpointURL(base, "/v1/videos"))
	if err != nil {
		return "", err
	}
	target.Path += "/" + taskID + "/content"
	return target.String(), nil
}

// Use the gateway's existing outbound policy/proxy/transport, but never its
// generation, scheduler, retry, or billing paths. Disconnect cancels the read.
func (s *OpenAIGatewayService) StreamAdminVideoPreview(c *gin.Context, account *Account, requestID string) error {
	target, err := s.adminVideoContentURL(account, requestID)
	if err != nil {
		return err
	}
	token := account.GetCredential("api_key")
	if account.IsGrokOAuth() {
		// Previewing an existing task must not trigger scheduler failure handling.
		token, _, err = s.GetAccessToken(c.Request.Context(), account)
		if err != nil {
			return err
		}
	}
	if token == "" {
		return fmt.Errorf("video account credential unavailable")
	}
	proxyURL := ""
	if account.ProxyID != nil && account.Proxy != nil {
		proxyURL = account.Proxy.URL()
	}
	signedContent := false
	if account.IsGrok() {
		// Native Grok returns a signed CDN URL rather than a /content payload.
		// Read its existing task status without completion/billing side effects.
		taskID, _ := adminVideoTaskID(requestID)
		statusURL, err := buildGrokMediaURL(account, s.cfg, GrokMediaEndpointVideoStatus, taskID)
		if err != nil {
			return err
		}
		statusReq, err := http.NewRequestWithContext(WithHTTPUpstreamRedirectsDisabled(c.Request.Context()), http.MethodGet, statusURL, nil)
		if err != nil {
			return err
		}
		statusReq.Header.Set("Authorization", "Bearer "+token)
		statusReq.Header.Set("Accept", "application/json")
		if account.IsGrokOAuth() && isGrokCLIProxyTarget(statusURL) {
			applyGrokCLIHeaders(statusReq.Header)
		}
		account.ApplyHeaderOverrides(statusReq.Header)
		statusResp, err := s.httpUpstream.Do(statusReq, proxyURL, account.ID, account.Concurrency)
		if err != nil {
			return err
		}
		body, readErr := io.ReadAll(io.LimitReader(statusResp.Body, (1<<20)+1))
		_ = statusResp.Body.Close()
		if readErr != nil || len(body) > 1<<20 || statusResp.StatusCode != http.StatusOK {
			return fmt.Errorf("video task status unavailable")
		}
		contentURL, err := grokMediaSignedVideoContentURL(body, taskID)
		if err != nil {
			return err
		}
		if contentURL != "" {
			target, signedContent = contentURL, true
		}
	}
	req, err := http.NewRequestWithContext(WithHTTPUpstreamRedirectsDisabled(c.Request.Context()), http.MethodGet, target, nil)
	if err != nil {
		return err
	}
	if !signedContent {
		req.Header.Set("Authorization", "Bearer "+token)
		if account.IsGrokOAuth() && isGrokCLIProxyTarget(target) {
			applyGrokCLIHeaders(req.Header)
		}
		account.ApplyHeaderOverrides(req.Header)
	}
	req.Header.Set("Accept", "video/*, application/octet-stream")
	for _, name := range []string{"Range", "If-Range"} {
		if value := c.GetHeader(name); value != "" {
			req.Header.Set(name, value)
		}
	}
	resp, err := s.httpUpstream.Do(req, proxyURL, account.ID, account.Concurrency)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusRequestedRangeNotSatisfiable {
		c.Header("Content-Range", resp.Header.Get("Content-Range"))
		c.Status(resp.StatusCode)
		return nil
	}
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		return fmt.Errorf("video content status %d", resp.StatusCode)
	}
	contentType := strings.ToLower(strings.Split(resp.Header.Get("Content-Type"), ";")[0])
	if !strings.HasPrefix(contentType, "video/") && contentType != "application/octet-stream" {
		return fmt.Errorf("upstream did not return video content")
	}
	return writeGrokMediaContentResponse(c, resp)
}
