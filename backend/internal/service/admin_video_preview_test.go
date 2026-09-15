package service

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

type adminVideoTransport struct {
	HTTPUpstream
	do func(*http.Request) (*http.Response, error)
}

func (s *adminVideoTransport) Do(r *http.Request, _ string, _ int64, _ int) (*http.Response, error) {
	return s.do(r)
}

func TestAdminVideoPreviewHistoricalRetention(t *testing.T) {
	now := time.Now()
	log := &UsageLog{ID: 12, VideoCount: 1, RequestID: "grok-video:wan_123", CreatedAt: now.Add(-time.Hour)}
	require.Equal(t, []string{"/api/v1/admin/usage/12/videos/0"}, ListAdminVideoPreviewURLs(log, now))
	log.CreatedAt = now.Add(-7 * 24 * time.Hour)
	require.Empty(t, ListAdminVideoPreviewURLs(log, now))
	log.CreatedAt = now.Add(time.Hour)
	require.Empty(t, ListAdminVideoPreviewURLs(log, now))
	require.Equal(t, videoPreviewKey("wan_123", 2), videoPreviewKey("grok-video:wan_123", 2))
	for _, id := range []string{"", "grok-video:", "grok-video:../secret", "wan_123?key=x", "https://evil.test/file", "wan%2f123"} {
		_, err := adminVideoTaskID(id)
		require.Error(t, err, id)
	}
}

func TestAdminVideoPreviewStreamRangeAndRejectUnsafeResponse(t *testing.T) {
	account := &Account{ID: 493, Platform: PlatformOpenAI, Type: AccountTypeAPIKey, Credentials: map[string]any{"base_url": "https://video.example/v1", "api_key": "test-secret"}}
	for _, tc := range []struct {
		status      int
		contentType string
		wantError   bool
	}{
		{200, "video/mp4", false}, {206, "video/mp4", false}, {416, "application/json", false},
		{302, "video/mp4", true}, {200, "text/html", true}, {200, "application/json", true}, {403, "application/json", true},
	} {
		t.Run(http.StatusText(tc.status)+tc.contentType, func(t *testing.T) {
			calls := 0
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			s := &OpenAIGatewayService{httpUpstream: &adminVideoTransport{do: func(r *http.Request) (*http.Response, error) {
				calls++
				require.Equal(t, http.MethodGet, r.Method)
				require.Equal(t, "https://video.example/v1/videos/wan_123/content", r.URL.String())
				require.Equal(t, "Bearer test-secret", r.Header.Get("Authorization"))
				require.Equal(t, "bytes=0-15", r.Header.Get("Range"))
				require.True(t, HTTPUpstreamRedirectsDisabled(r.Context()))
				cancel()
				require.ErrorIs(t, r.Context().Err(), context.Canceled)
				return &http.Response{StatusCode: tc.status, Header: http.Header{"Content-Type": {tc.contentType}, "Content-Range": {"bytes 0-15/100"}}, Body: io.NopCloser(strings.NewReader("0123456789abcdef")), ContentLength: 16}, nil
			}}}
			w := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(w)
			c.Request = httptest.NewRequest(http.MethodGet, "/preview", nil).WithContext(ctx)
			c.Request.Header.Set("Range", "bytes=0-15")
			err := s.StreamAdminVideoPreview(c, account, "grok-video:wan_123")
			require.Equal(t, tc.wantError, err != nil)
			require.Equal(t, 1, calls)
			if !tc.wantError {
				require.Equal(t, tc.status, c.Writer.Status())
			}
			if tc.status == 206 {
				require.Equal(t, "bytes 0-15/100", w.Header().Get("Content-Range"))
			}
			if tc.wantError {
				require.Empty(t, w.Body.String())
			}
		})
	}
}

func TestAdminVideoPreviewGrokSignedContentNeverReceivesCredentials(t *testing.T) {
	account := &Account{ID: 7, Platform: PlatformGrok, Type: AccountTypeAPIKey, Credentials: map[string]any{"base_url": "https://api.x.ai", "api_key": "test-secret"}}
	for _, target := range []string{"https://vidgen.x.ai/test.mp4?sig=test", "https://evil.example/test.mp4"} {
		calls := 0
		s := &OpenAIGatewayService{httpUpstream: &adminVideoTransport{do: func(r *http.Request) (*http.Response, error) {
			calls++
			require.Equal(t, http.MethodGet, r.Method)
			require.True(t, HTTPUpstreamRedirectsDisabled(r.Context()))
			if calls == 1 {
				require.Equal(t, "api.x.ai", r.URL.Hostname())
				require.Equal(t, "Bearer test-secret", r.Header.Get("Authorization"))
				return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"status":"done","video":{"url":"` + target + `"}}`))}, nil
			}
			require.Equal(t, "vidgen.x.ai", r.URL.Hostname())
			require.Empty(t, r.Header.Get("Authorization"))
			require.Equal(t, "bytes=0-15", r.Header.Get("Range"))
			return &http.Response{StatusCode: 206, Header: http.Header{"Content-Type": {"video/mp4"}}, Body: io.NopCloser(strings.NewReader("0123456789abcdef")), ContentLength: 16}, nil
		}}}
		c, _ := gin.CreateTestContext(httptest.NewRecorder())
		c.Request = httptest.NewRequest(http.MethodGet, "/preview", nil)
		c.Request.Header.Set("Range", "bytes=0-15")
		err := s.StreamAdminVideoPreview(c, account, "grok-video:task_123")
		if strings.Contains(target, "evil.example") {
			require.Error(t, err)
			require.Equal(t, 1, calls)
		} else {
			require.NoError(t, err)
			require.Equal(t, 2, calls)
		}
	}
}
