package service

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/tidwall/gjson"
	"github.com/Wei-Shaw/sub2api/internal/pkg/logger"
	"github.com/gin-gonic/gin"
)

const (
	openAIImagePreviewContextKey = "openai_image_preview_bytes"
	openAIImagePreviewDir        = "/app/data/admin-image-previews"
	openAIImagePreviewMaxCount   = 8
	openAIImagePreviewMaxBytes   = 20 << 20
	adminVideoPreviewDir         = "/app/data/admin-video-previews"
	adminVideoPreviewMaxBytes    = 100 << 20
	adminVideoPreviewRetention   = 7 * 24 * time.Hour
)

// OpenAIImagePreviewAsset is an in-memory image returned by a synchronous image request.
// It is intentionally never exposed through a regular user DTO.
type OpenAIImagePreviewAsset struct {
	Data        []byte
	ContentType string
	DownloadURL string
}

func extractOpenAIImagePreviewAssets(body []byte) []OpenAIImagePreviewAsset {
	assets := collectOpenAIImageInlineAssets(body, "")
	if len(assets) == 0 {
		return nil
	}
	out := make([]OpenAIImagePreviewAsset, 0, minInt(len(assets), openAIImagePreviewMaxCount))
	seen := make(map[string]struct{}, len(assets))
	for _, asset := range assets {
		raw := strings.TrimSpace(asset.B64JSON)
		if raw == "" {
			raw = strings.TrimSpace(asset.DownloadURL)
		}
		encoded := normalizeOpenAIImageBase64(raw)
		if encoded != "" {
			data, err := decodeOpenAIImageBase64(encoded)
			if err != nil || len(data) == 0 || len(data) > openAIImagePreviewMaxBytes {
				continue
			}
			digest := sha256.Sum256(data)
			key := hex.EncodeToString(digest[:])
			if _, ok := seen[key]; ok {
				continue
			}
			seen[key] = struct{}{}
			contentType := strings.TrimSpace(asset.MimeType)
			if contentType == "" {
				contentType = http.DetectContentType(data)
			}
			if !strings.HasPrefix(strings.ToLower(contentType), "image/") {
				continue
			}
			out = append(out, OpenAIImagePreviewAsset{Data: data, ContentType: contentType})
		} else if downloadURL := strings.TrimSpace(asset.DownloadURL); isPreviewDownloadURL(downloadURL) {
			key := "url:" + downloadURL
			if _, ok := seen[key]; ok {
				continue
			}
			seen[key] = struct{}{}
			out = append(out, OpenAIImagePreviewAsset{DownloadURL: downloadURL, ContentType: strings.TrimSpace(asset.MimeType)})
		}
		if len(out) >= openAIImagePreviewMaxCount {
			break
		}
	}
	return out
}

func decodeOpenAIImageBase64(encoded string) ([]byte, error) {
	// normalizeOpenAIImageBase64 has already validated the standard encoding.
	return base64.StdEncoding.DecodeString(encoded)
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func setOpenAIImagePreviewAssets(c *gin.Context, assets []OpenAIImagePreviewAsset) {
	if c != nil && len(assets) > 0 {
		c.Set(openAIImagePreviewContextKey, assets)
	}
}

// CaptureOpenAIImagePreviewResponse extracts image data from an upstream JSON/SSE payload.
// It is safe to call for every streamed event; duplicate assets are removed.
func CaptureOpenAIImagePreviewResponse(c *gin.Context, body []byte) {
	appendOpenAIImagePreviewAssets(c, extractOpenAIImagePreviewAssets(body))
}

func appendOpenAIImagePreviewAssets(c *gin.Context, assets []OpenAIImagePreviewAsset) {
	if c == nil || len(assets) == 0 {
		return
	}
	existing := OpenAIImagePreviewAssetsFromContext(c)
	merged := append(append([]OpenAIImagePreviewAsset(nil), existing...), assets...)
	seen := make(map[string]struct{}, len(merged))
	out := make([]OpenAIImagePreviewAsset, 0, minInt(len(merged), openAIImagePreviewMaxCount))
	for _, asset := range merged {
		key := strings.TrimSpace(asset.DownloadURL)
		if len(asset.Data) > 0 {
			digest := sha256.Sum256(asset.Data)
			key = hex.EncodeToString(digest[:])
		}
		if key == "" {
			continue
		}
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, asset)
		if len(out) >= openAIImagePreviewMaxCount {
			break
		}
	}
	setOpenAIImagePreviewAssets(c, out)
}

// OpenAIImagePreviewAssetsFromContext returns assets captured by the non-streaming handler.
func OpenAIImagePreviewAssetsFromContext(c *gin.Context) []OpenAIImagePreviewAsset {
	if c == nil {
		return nil
	}
	value, ok := c.Get(openAIImagePreviewContextKey)
	if !ok {
		return nil
	}
	assets, _ := value.([]OpenAIImagePreviewAsset)
	return assets
}

// SaveOpenAIImagePreviewsAsync queues a best-effort disk write without delaying billing.
func SaveOpenAIImagePreviewsAsync(ctx context.Context, assets []OpenAIImagePreviewAsset, requestID string, apiKeyID int64) {
	if len(assets) == 0 {
		return
	}
	go func() {
		if err := SaveOpenAIImagePreviews(assets, requestID, apiKeyID); err != nil {
			logger.LegacyPrintf("service.image_preview", "save image previews failed: %v", err)
		}
	}()
}

func isPreviewDownloadURL(raw string) bool {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || u.Host == "" {
		return false
	}
	return (strings.EqualFold(u.Scheme, "https") || strings.EqualFold(u.Scheme, "http")) && !strings.EqualFold(u.Hostname(), "localhost")
}

func downloadOpenAIImagePreview(urlValue string) ([]byte, string, error) {
	if !isPreviewDownloadURL(urlValue) {
		return nil, "", fmt.Errorf("invalid image preview URL")
	}
	client := &http.Client{Timeout: 15 * time.Second}
	request, err := http.NewRequest(http.MethodGet, urlValue, nil)
	if err != nil {
		return nil, "", err
	}
	request.Header.Set("Accept", "image/*,*/*;q=0.8")
	response, err := client.Do(request)
	if err != nil {
		return nil, "", err
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return nil, "", fmt.Errorf("image preview download returned status %d", response.StatusCode)
	}
	if response.ContentLength > openAIImagePreviewMaxBytes {
		return nil, "", fmt.Errorf("image preview exceeds size limit")
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, openAIImagePreviewMaxBytes+1))
	if err != nil {
		return nil, "", err
	}
	if len(data) == 0 || len(data) > openAIImagePreviewMaxBytes {
		return nil, "", fmt.Errorf("invalid image preview size")
	}
	contentType := http.DetectContentType(data)
	if !strings.HasPrefix(strings.ToLower(contentType), "image/") {
		return nil, "", fmt.Errorf("downloaded preview is not an image")
	}
	return data, contentType, nil
}

// ResolveUsageRecordID applies the same request-id precedence used by usage billing.
func ResolveUsageRecordID(ctx context.Context, upstreamRequestID string) string {
	return resolveUsageBillingRequestID(ctx, upstreamRequestID)
}

func imagePreviewKey(requestID string, apiKeyID int64) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(requestID) + "\x1f" + strconv.FormatInt(apiKeyID, 10)))
	return hex.EncodeToString(sum[:])
}

// SaveOpenAIImagePreviews persists generated images outside the database.
func SaveOpenAIImagePreviews(assets []OpenAIImagePreviewAsset, requestID string, apiKeyID int64) error {
	if len(assets) == 0 || strings.TrimSpace(requestID) == "" || apiKeyID <= 0 {
		return nil
	}
	dir := filepath.Join(openAIImagePreviewDir, imagePreviewKey(requestID, apiKeyID))
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	for index, asset := range assets {
		if index >= openAIImagePreviewMaxCount {
			continue
		}
		if len(asset.Data) == 0 && strings.TrimSpace(asset.DownloadURL) != "" {
			data, contentType, err := downloadOpenAIImagePreview(asset.DownloadURL)
			if err != nil {
				logger.LegacyPrintf("service.image_preview", "download image preview failed: %v", err)
				continue
			}
			asset.Data = data
			asset.ContentType = contentType
		}
		if len(asset.Data) == 0 || len(asset.Data) > openAIImagePreviewMaxBytes {
			continue
		}
		ext := ".bin"
		if strings.EqualFold(strings.TrimSpace(asset.ContentType), "image/png") {
			ext = ".png"
		} else if strings.EqualFold(strings.TrimSpace(asset.ContentType), "image/jpeg") {
			ext = ".jpg"
		} else if strings.EqualFold(strings.TrimSpace(asset.ContentType), "image/webp") {
			ext = ".webp"
		}
		target := filepath.Join(dir, strconv.Itoa(index)+ext)
		tmp, err := os.CreateTemp(dir, ".preview-*")
		if err != nil {
			return err
		}
		if err = tmp.Chmod(0600); err == nil {
			_, err = tmp.Write(asset.Data)
		}
		closeErr := tmp.Close()
		if err == nil {
			err = closeErr
		}
		if err == nil {
			err = os.Rename(tmp.Name(), target)
		} else {
			_ = os.Remove(tmp.Name())
		}
		if err != nil {
			return fmt.Errorf("write image preview %d: %w", index, err)
		}
	}
	return nil
}

// ReadOpenAIImagePreview reads one preview for an authenticated admin handler.
func ReadOpenAIImagePreview(requestID string, apiKeyID int64, index int) ([]byte, string, error) {
	if index < 0 || index >= openAIImagePreviewMaxCount {
		return nil, "", os.ErrNotExist
	}
	dir := filepath.Join(openAIImagePreviewDir, imagePreviewKey(requestID, apiKeyID))
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, "", err
	}
	prefix := strconv.Itoa(index)
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasPrefix(entry.Name(), prefix+".") {
			continue
		}
		data, readErr := os.ReadFile(filepath.Join(dir, entry.Name()))
		if readErr != nil {
			return nil, "", readErr
		}
		return data, http.DetectContentType(data), nil
	}
	return nil, "", os.ErrNotExist
}

// ListOpenAIImagePreviewURLs returns only files that actually exist on disk.
func ListOpenAIImagePreviewURLs(requestID string, apiKeyID, usageID int64, imageCount int) []string {
	if imageCount <= 0 {
		return nil
	}
	limit := minInt(imageCount, openAIImagePreviewMaxCount)
	urls := make([]string, 0, limit)
	for index := 0; index < limit; index++ {
		if _, _, err := ReadOpenAIImagePreview(requestID, apiKeyID, index); err == nil {
			urls = append(urls, fmt.Sprintf("/api/v1/admin/usage/%d/images/%d", usageID, index))
		}
	}
	return urls
}

// SaveGrokVideoPreviewAsync persists a completed video without delaying the client response.
func SaveGrokVideoPreviewAsync(videoURL, requestID string, apiKeyID int64) {
	if strings.TrimSpace(videoURL) == "" || strings.TrimSpace(requestID) == "" || apiKeyID <= 0 {
		return
	}
	go func() {
		if err := saveGrokVideoPreview(videoURL, requestID, apiKeyID); err != nil {
			logger.LegacyPrintf("service.video_preview", "save video preview failed: %v", err)
		}
	}()
}

func videoPreviewKey(requestID string, apiKeyID int64) string {
	// Capture and usage billing must resolve to the same directory.
	requestID = StableGrokVideoBillingRequestID(strings.TrimSpace(requestID))
	sum := sha256.Sum256([]byte(requestID + "\x1f" + strconv.FormatInt(apiKeyID, 10)))
	return hex.EncodeToString(sum[:])
}

func saveGrokVideoPreview(videoURL, requestID string, apiKeyID int64) error {
	if !isTrustedVideoPreviewURL(videoURL) {
		return fmt.Errorf("invalid grok video preview URL")
	}
	dir := filepath.Join(adminVideoPreviewDir, videoPreviewKey(requestID, apiKeyID))
	if err := os.MkdirAll(dir, 0700); err != nil { return err }
	tmp, err := os.CreateTemp(dir, ".preview-url-*")
	if err != nil { return err }
	if err = tmp.Chmod(0600); err == nil { _, err = io.WriteString(tmp, strings.TrimSpace(videoURL)) }
	closeErr := tmp.Close(); if err == nil { err = closeErr }
	if err == nil { err = os.Rename(tmp.Name(), filepath.Join(dir, "0.url")) } else { _ = os.Remove(tmp.Name()) }
	return err
}

func bytesLooksLikeMP4(data []byte) bool {
	return len(data) >= 12 && string(data[4:8]) == "ftyp"
}

func ReadGrokVideoPreview(requestID string, apiKeyID int64) ([]byte, string, error) {
	if strings.TrimSpace(requestID) == "" || apiKeyID <= 0 { return nil, "", os.ErrNotExist }
	data, err := os.ReadFile(filepath.Join(adminVideoPreviewDir, videoPreviewKey(requestID, apiKeyID), "0.url"))
	if os.IsNotExist(err) {
		// Earlier releases captured the raw task ID before adding the billing prefix.
		rawID := strings.TrimPrefix(strings.TrimSpace(requestID), "grok-video:")
		sum := sha256.Sum256([]byte(rawID + "\x1f" + strconv.FormatInt(apiKeyID, 10)))
		data, err = os.ReadFile(filepath.Join(adminVideoPreviewDir, hex.EncodeToString(sum[:]), "0.url"))
	}
	if err != nil { return nil, "", err }
	return data, "text/uri-list", nil
}

func ListGrokVideoPreviewURLs(requestID string, apiKeyID, usageID int64, videoCount int) []string {
	if videoCount <= 0 { return nil }
	if _, _, err := ReadGrokVideoPreview(requestID, apiKeyID); err != nil { return nil }
	return []string{fmt.Sprintf("/api/v1/admin/usage/%d/videos/0", usageID)}
}

// CleanupAdminMediaPreviews removes image/video preview directories older than the retention window.
func CleanupAdminMediaPreviews(now time.Time) error {
	cutoff := now.Add(-adminVideoPreviewRetention)
	for _, root := range []string{openAIImagePreviewDir, adminVideoPreviewDir} {
		entries, err := os.ReadDir(root)
		if os.IsNotExist(err) { continue }
		if err != nil { return err }
		for _, entry := range entries {
			if !entry.IsDir() { continue }
			path := filepath.Join(root, entry.Name())
			info, err := entry.Info(); if err != nil { continue }
			if info.ModTime().Before(cutoff) { _ = os.RemoveAll(path) }
		}
	}
	return nil
}

// ExtractVideoPreviewURL finds a provider video URL in common OpenAI-compatible responses.
func ExtractVideoPreviewURL(body []byte) string {
	if !gjson.ValidBytes(body) { return "" }
	for _, path := range []string{"video.url", "video_url", "url", "download_url", "output.video_url", "output.url", "data.0.video.url", "data.0.video_url", "data.0.url"} {
		value := strings.TrimSpace(gjson.GetBytes(body, path).String())
		if isTrustedVideoPreviewURL(value) && (path != "data.0.url" || looksLikeVideoURL(value)) { return value }
	}
	return ""
}

func looksLikeVideoURL(raw string) bool {
	path := strings.ToLower(strings.SplitN(strings.TrimSpace(raw), "?", 2)[0])
	for _, ext := range []string{".mp4", ".webm", ".mov", ".mkv", ".avi", ".m3u8"} {
		if strings.HasSuffix(path, ext) { return true }
	}
	return strings.Contains(path, "video") || strings.Contains(path, "media")
}

func isTrustedVideoPreviewURL(raw string) bool {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || !strings.EqualFold(u.Scheme, "https") || u.User != nil || u.Hostname() == "" { return false }
	// Provider domains are intentionally limited to known media hosts; arbitrary URLs
	// in model text must never be fetched by the server.
	host := strings.ToLower(u.Hostname())
	return host == "vidgen.x.ai" || strings.Contains(host, "wan") || strings.Contains(host, "aliyuncs.com") || strings.Contains(host, "volces.com") || strings.Contains(host, "modelscope.cn") || strings.Contains(host, "tencentcos.cn") || strings.Contains(host, "cloudflarestorage.com") || strings.Contains(host, "replicate.delivery") || strings.Contains(host, "huggingface.co") || strings.HasSuffix(host, ".r2.dev") || strings.Contains(host, "amazonaws.com")
}
