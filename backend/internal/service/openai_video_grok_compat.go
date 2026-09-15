package service

import (
	"strings"

	"github.com/tidwall/gjson"
	"github.com/tidwall/sjson"
)

// Only explicitly configured Grok-compatible relays use these status names.
// Native OpenAI/New API responses remain unchanged.
func normalizeOpenAIVideoResponse(account *Account, body []byte) []byte {
	if isZhongYVideoProtocol(account) {
		return normalizeZhongYVideoResponse(body)
	}
	if !isOpenAIGrokVideoProtocol(account) {
		return body
	}
	status := strings.ToLower(strings.TrimSpace(gjson.GetBytes(body, "status").String()))
	switch status {
	case "pending":
		status = "queued"
	case "processing", "running":
		status = "in_progress"
	case "done":
		hasContent := false
		for _, path := range []string{"video.url", "url", "video_url", "result_url", "download_url"} {
			value := gjson.GetBytes(body, path)
			if value.Type == gjson.String && strings.TrimSpace(value.String()) != "" {
				hasContent = true
				break
			}
		}
		if !hasContent {
			return body
		}
		status = "completed"
	default:
		return body
	}
	if rewritten, err := sjson.SetBytes(body, "status", status); err == nil {
		return rewritten
	}
	return body
}
