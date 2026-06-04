#include <Arduino.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <WiFi.h>
#include "esp_camera.h"

#if __has_include("secrets.h")
#include "secrets.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

#define CAMERA_NAME "rpg-esp32s3-webcam"
#define AP_SSID "RPG-ESP32S3-CAM"
#define AP_PASSWORD "projector"

// Freenove ESP32-S3 WROOM camera pin map, matching its ESP32S3_EYE example.
#define PWDN_GPIO_NUM -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 15
#define SIOD_GPIO_NUM 4
#define SIOC_GPIO_NUM 5
#define Y2_GPIO_NUM 11
#define Y3_GPIO_NUM 9
#define Y4_GPIO_NUM 8
#define Y5_GPIO_NUM 10
#define Y6_GPIO_NUM 12
#define Y7_GPIO_NUM 18
#define Y8_GPIO_NUM 17
#define Y9_GPIO_NUM 16
#define VSYNC_GPIO_NUM 6
#define HREF_GPIO_NUM 7
#define PCLK_GPIO_NUM 13

WebServer server(80);

static constexpr framesize_t INITIAL_PSRAM_FRAME_SIZE = FRAMESIZE_UXGA;
static constexpr framesize_t DEFAULT_FRAME_SIZE = FRAMESIZE_VGA;

static const char *frameSizeName(framesize_t frameSize) {
  switch (frameSize) {
    case FRAMESIZE_QQVGA: return "qqvga";
    case FRAMESIZE_QVGA: return "qvga";
    case FRAMESIZE_VGA: return "vga";
    case FRAMESIZE_SVGA: return "svga";
    case FRAMESIZE_XGA: return "xga";
    case FRAMESIZE_HD: return "hd";
    case FRAMESIZE_SXGA: return "sxga";
    case FRAMESIZE_UXGA: return "uxga";
    case FRAMESIZE_FHD: return "fhd";
    case FRAMESIZE_P_HD: return "p_hd";
    case FRAMESIZE_P_3MP: return "p_3mp";
    case FRAMESIZE_QXGA: return "qxga";
    case FRAMESIZE_QSXGA: return "qsxga";
    default: return "unknown";
  }
}

static uint16_t frameSizeWidth(framesize_t frameSize) {
  switch (frameSize) {
    case FRAMESIZE_QQVGA: return 160;
    case FRAMESIZE_QVGA: return 320;
    case FRAMESIZE_VGA: return 640;
    case FRAMESIZE_SVGA: return 800;
    case FRAMESIZE_XGA: return 1024;
    case FRAMESIZE_HD: return 1280;
    case FRAMESIZE_SXGA: return 1280;
    case FRAMESIZE_UXGA: return 1600;
    case FRAMESIZE_FHD: return 1920;
    case FRAMESIZE_P_HD: return 720;
    case FRAMESIZE_P_3MP: return 864;
    case FRAMESIZE_QXGA: return 2048;
    case FRAMESIZE_QSXGA: return 2560;
    default: return 0;
  }
}

static uint16_t frameSizeHeight(framesize_t frameSize) {
  switch (frameSize) {
    case FRAMESIZE_QQVGA: return 120;
    case FRAMESIZE_QVGA: return 240;
    case FRAMESIZE_VGA: return 480;
    case FRAMESIZE_SVGA: return 600;
    case FRAMESIZE_XGA: return 768;
    case FRAMESIZE_HD: return 720;
    case FRAMESIZE_SXGA: return 1024;
    case FRAMESIZE_UXGA: return 1200;
    case FRAMESIZE_FHD: return 1080;
    case FRAMESIZE_P_HD: return 1280;
    case FRAMESIZE_P_3MP: return 1536;
    case FRAMESIZE_QXGA: return 1536;
    case FRAMESIZE_QSXGA: return 1920;
    default: return 0;
  }
}

static const char *sensorName(uint16_t pid) {
  switch (pid) {
    case OV2640_PID: return "OV2640";
    case OV3660_PID: return "OV3660";
    case OV5640_PID: return "OV5640";
    default: return "unknown";
  }
}

static bool sensorMaxFrameSize(uint16_t pid, framesize_t &frameSize) {
  switch (pid) {
    case OV2640_PID:
      frameSize = FRAMESIZE_UXGA;
      return true;
    case OV3660_PID:
      frameSize = FRAMESIZE_QXGA;
      return true;
    case OV5640_PID:
      frameSize = FRAMESIZE_QSXGA;
      return true;
    default:
      return false;
  }
}

static bool parseFrameSize(String value, sensor_t *sensor, framesize_t &frameSize) {
  value.trim();
  value.toLowerCase();
  value.replace("-", "_");

  if (value.length() == 0 || value == "default" || value == "preview" || value == "vga") {
    frameSize = DEFAULT_FRAME_SIZE;
    return true;
  }
  if (value == "qqvga") {
    frameSize = FRAMESIZE_QQVGA;
    return true;
  }
  if (value == "qvga") {
    frameSize = FRAMESIZE_QVGA;
    return true;
  }
  if (value == "svga") {
    frameSize = FRAMESIZE_SVGA;
    return true;
  }
  if (value == "xga") {
    frameSize = FRAMESIZE_XGA;
    return true;
  }
  if (value == "hd") {
    frameSize = FRAMESIZE_HD;
    return true;
  }
  if (value == "sxga") {
    frameSize = FRAMESIZE_SXGA;
    return true;
  }
  if (value == "uxga" || value == "2mp") {
    frameSize = FRAMESIZE_UXGA;
    return true;
  }
  if (value == "qxga" || value == "3mp") {
    frameSize = FRAMESIZE_QXGA;
    return true;
  }
  if (value == "max") {
    return sensor && sensorMaxFrameSize(sensor->id.PID, frameSize);
  }

  return false;
}

static void appendFrameSizeJson(String &payload, const char *key, framesize_t frameSize) {
  payload += "\"";
  payload += key;
  payload += "\":{\"name\":\"";
  payload += frameSizeName(frameSize);
  payload += "\",\"width\":";
  payload += frameSizeWidth(frameSize);
  payload += ",\"height\":";
  payload += frameSizeHeight(frameSize);
  payload += "}";
}

static void appendSensorStatusJson(String &payload, sensor_t *sensor) {
  payload += "\"sensorSettings\":{";
  if (!sensor) {
    payload += "\"available\":false}";
    return;
  }

  camera_status_t status = sensor->status;
  payload += "\"available\":true,";
  payload += "\"quality\":";
  payload += status.quality;
  payload += ",\"brightness\":";
  payload += status.brightness;
  payload += ",\"contrast\":";
  payload += status.contrast;
  payload += ",\"saturation\":";
  payload += status.saturation;
  payload += ",\"sharpness\":";
  payload += status.sharpness;
  payload += ",\"denoise\":";
  payload += status.denoise;
  payload += ",\"aec\":";
  payload += status.aec;
  payload += ",\"aec2\":";
  payload += status.aec2;
  payload += ",\"aeLevel\":";
  payload += status.ae_level;
  payload += ",\"aecValue\":";
  payload += status.aec_value;
  payload += ",\"agc\":";
  payload += status.agc;
  payload += ",\"agcGain\":";
  payload += status.agc_gain;
  payload += ",\"gainCeiling\":";
  payload += status.gainceiling;
  payload += ",\"awb\":";
  payload += status.awb;
  payload += ",\"awbGain\":";
  payload += status.awb_gain;
  payload += ",\"wbMode\":";
  payload += status.wb_mode;
  payload += ",\"vflip\":";
  payload += status.vflip;
  payload += ",\"hmirror\":";
  payload += status.hmirror;
  payload += ",\"lenc\":";
  payload += status.lenc;
  payload += ",\"rawGma\":";
  payload += status.raw_gma;
  payload += "}";
}

static int clampControlValue(int value, int minimum, int maximum) {
  return max(minimum, min(maximum, value));
}

static bool applySensorControl(sensor_t *sensor, String variable, int value, String &message) {
  if (!sensor) {
    message = "Camera sensor unavailable";
    return false;
  }

  variable.trim();
  variable.toLowerCase();
  variable.replace("-", "_");

  int result = -1;
  if (variable == "quality") {
    result = sensor->set_quality(sensor, clampControlValue(value, 4, 63));
  } else if (variable == "brightness") {
    result = sensor->set_brightness(sensor, clampControlValue(value, -2, 2));
  } else if (variable == "contrast") {
    result = sensor->set_contrast(sensor, clampControlValue(value, -2, 2));
  } else if (variable == "saturation") {
    result = sensor->set_saturation(sensor, clampControlValue(value, -2, 2));
  } else if (variable == "sharpness") {
    result = sensor->set_sharpness(sensor, clampControlValue(value, -2, 2));
  } else if (variable == "denoise") {
    result = sensor->set_denoise(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "gainceiling" || variable == "gain_ceiling") {
    result = sensor->set_gainceiling(sensor, static_cast<gainceiling_t>(clampControlValue(value, 0, 6)));
  } else if (variable == "aec" || variable == "exposure_ctrl") {
    result = sensor->set_exposure_ctrl(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "aec2") {
    result = sensor->set_aec2(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "ae_level") {
    result = sensor->set_ae_level(sensor, clampControlValue(value, -2, 2));
  } else if (variable == "aec_value") {
    result = sensor->set_aec_value(sensor, clampControlValue(value, 0, 1200));
  } else if (variable == "agc" || variable == "gain_ctrl") {
    result = sensor->set_gain_ctrl(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "agc_gain") {
    result = sensor->set_agc_gain(sensor, clampControlValue(value, 0, 30));
  } else if (variable == "awb" || variable == "whitebal") {
    result = sensor->set_whitebal(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "awb_gain") {
    result = sensor->set_awb_gain(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "wb_mode") {
    result = sensor->set_wb_mode(sensor, clampControlValue(value, 0, 4));
  } else if (variable == "vflip") {
    result = sensor->set_vflip(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "hmirror") {
    result = sensor->set_hmirror(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "lenc") {
    result = sensor->set_lenc(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "raw_gma") {
    result = sensor->set_raw_gma(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "bpc") {
    result = sensor->set_bpc(sensor, clampControlValue(value, 0, 1));
  } else if (variable == "wpc") {
    result = sensor->set_wpc(sensor, clampControlValue(value, 0, 1));
  } else {
    message = "Unsupported control variable";
    return false;
  }

  if (result != 0) {
    message = "Sensor rejected control change";
    return false;
  }

  message = "ok";
  delay(80);
  return true;
}

static bool applyBrightMatPreset(sensor_t *sensor, String &message) {
  if (!sensor) {
    message = "Camera sensor unavailable";
    return false;
  }

  int requiredFailures = 0;
  int optionalFailures = 0;
  auto apply = [&](int result, bool required) {
    if (result == 0) return;
    if (required) {
      requiredFailures += 1;
    } else {
      optionalFailures += 1;
    }
  };

  apply(sensor->set_quality(sensor, 8), true);
  apply(sensor->set_brightness(sensor, 2), true);
  apply(sensor->set_contrast(sensor, 1), true);
  apply(sensor->set_saturation(sensor, 0), true);
  apply(sensor->set_sharpness(sensor, 1), false);
  apply(sensor->set_denoise(sensor, 1), false);
  apply(sensor->set_exposure_ctrl(sensor, 1), true);
  apply(sensor->set_aec2(sensor, 1), false);
  apply(sensor->set_ae_level(sensor, 2), false);
  apply(sensor->set_gain_ctrl(sensor, 1), true);
  apply(sensor->set_agc_gain(sensor, 20), false);
  apply(sensor->set_gainceiling(sensor, GAINCEILING_32X), false);
  apply(sensor->set_whitebal(sensor, 1), true);
  apply(sensor->set_awb_gain(sensor, 1), true);
  apply(sensor->set_lenc(sensor, 1), false);
  apply(sensor->set_raw_gma(sensor, 1), false);

  const bool ok = requiredFailures == 0;
  if (ok && optionalFailures > 0) {
    message = "ok; optional controls unsupported: ";
    message += optionalFailures;
  } else if (ok) {
    message = "ok";
  } else {
    message = "Required bright-mat preset controls failed: ";
    message += requiredFailures;
  }
  delay(160);
  return ok;
}

static bool applyDefaultPreset(sensor_t *sensor, String &message) {
  if (!sensor) {
    message = "Camera sensor unavailable";
    return false;
  }

  int requiredFailures = 0;
  int optionalFailures = 0;
  auto apply = [&](int result, bool required) {
    if (result == 0) return;
    if (required) {
      requiredFailures += 1;
    } else {
      optionalFailures += 1;
    }
  };

  apply(sensor->set_quality(sensor, 12), true);
  apply(sensor->set_brightness(sensor, 1), true);
  apply(sensor->set_contrast(sensor, 0), true);
  apply(sensor->set_saturation(sensor, 0), true);
  apply(sensor->set_sharpness(sensor, 0), false);
  apply(sensor->set_denoise(sensor, 0), false);
  apply(sensor->set_exposure_ctrl(sensor, 1), true);
  apply(sensor->set_aec2(sensor, 0), false);
  apply(sensor->set_ae_level(sensor, 0), false);
  apply(sensor->set_gain_ctrl(sensor, 1), true);
  apply(sensor->set_agc_gain(sensor, 0), false);
  apply(sensor->set_gainceiling(sensor, GAINCEILING_2X), false);
  apply(sensor->set_whitebal(sensor, 1), true);
  apply(sensor->set_awb_gain(sensor, 1), true);
  apply(sensor->set_vflip(sensor, 1), true);
  apply(sensor->set_hmirror(sensor, 0), true);
  apply(sensor->set_lenc(sensor, 1), false);
  apply(sensor->set_raw_gma(sensor, 1), false);

  const bool ok = requiredFailures == 0;
  if (ok && optionalFailures > 0) {
    message = "ok; optional controls unsupported: ";
    message += optionalFailures;
  } else if (ok) {
    message = "ok";
  } else {
    message = "Required default preset controls failed: ";
    message += requiredFailures;
  }
  delay(160);
  return ok;
}

static bool setCameraFrameSize(sensor_t *sensor, framesize_t frameSize) {
  if (!sensor) return false;
  if (sensor->status.framesize == frameSize) return true;

  const int result = sensor->set_framesize(sensor, frameSize);
  if (result != 0) {
    Serial.printf("Failed to set frame size %s (%d): %d\n", frameSizeName(frameSize), frameSize, result);
    return false;
  }

  if (frameSize >= FRAMESIZE_UXGA) {
    delay(900);
  } else if (frameSize >= FRAMESIZE_SXGA) {
    delay(600);
  } else if (frameSize >= FRAMESIZE_XGA) {
    delay(360);
  } else {
    delay(180);
  }
  return true;
}

static bool jpegFrameDimensions(const uint8_t *buffer, size_t length, uint16_t &width, uint16_t &height) {
  if (!buffer || length < 4 || buffer[0] != 0xff || buffer[1] != 0xd8) {
    return false;
  }

  size_t offset = 2;
  while (offset + 3 < length) {
    while (offset < length && buffer[offset] != 0xff) {
      offset += 1;
    }
    while (offset < length && buffer[offset] == 0xff) {
      offset += 1;
    }
    if (offset >= length) return false;

    const uint8_t marker = buffer[offset++];
    if (marker == 0xda || marker == 0xd9) return false;
    if (marker == 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
      continue;
    }
    if (offset + 2 > length) return false;

    const uint16_t segmentLength =
      (static_cast<uint16_t>(buffer[offset]) << 8) | buffer[offset + 1];
    if (segmentLength < 2 || offset + segmentLength > length) return false;

    const bool isStartOfFrame =
      (marker >= 0xc0 && marker <= 0xc3) ||
      (marker >= 0xc5 && marker <= 0xc7) ||
      (marker >= 0xc9 && marker <= 0xcb) ||
      (marker >= 0xcd && marker <= 0xcf);
    if (isStartOfFrame) {
      if (segmentLength < 7) return false;
      height = (static_cast<uint16_t>(buffer[offset + 3]) << 8) | buffer[offset + 4];
      width = (static_cast<uint16_t>(buffer[offset + 5]) << 8) | buffer[offset + 6];
      return true;
    }

    offset += segmentLength;
  }

  return false;
}

static bool frameBufferDimensions(camera_fb_t *fb, uint16_t &width, uint16_t &height) {
  if (!fb) return false;
  if (fb->format == PIXFORMAT_JPEG && jpegFrameDimensions(fb->buf, fb->len, width, height)) {
    return true;
  }

  width = fb->width;
  height = fb->height;
  return width > 0 && height > 0;
}

static bool frameBufferMatches(camera_fb_t *fb, framesize_t frameSize) {
  const uint16_t expectedWidth = frameSizeWidth(frameSize);
  const uint16_t expectedHeight = frameSizeHeight(frameSize);
  uint16_t actualWidth = 0;
  uint16_t actualHeight = 0;
  if (!frameBufferDimensions(fb, actualWidth, actualHeight)) return false;

  return expectedWidth == 0 || expectedHeight == 0 ||
    (actualWidth == expectedWidth && actualHeight == expectedHeight);
}

static unsigned long captureTimeoutMs(framesize_t frameSize) {
  if (frameSize >= FRAMESIZE_UXGA) return 20000;
  if (frameSize >= FRAMESIZE_SXGA) return 12000;
  if (frameSize >= FRAMESIZE_XGA) return 6000;
  return 3500;
}

static camera_fb_t *captureFrame(framesize_t requestedFrameSize) {
  const unsigned long deadline = millis() + captureTimeoutMs(requestedFrameSize);
  int mismatchedFrames = 0;

  while (millis() < deadline) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      delay(80);
      continue;
    }

    if (frameBufferMatches(fb, requestedFrameSize)) {
      return fb;
    }

    mismatchedFrames += 1;
    uint16_t actualWidth = 0;
    uint16_t actualHeight = 0;
    frameBufferDimensions(fb, actualWidth, actualHeight);
    Serial.printf(
      "Discarding stale %ux%u JPEG while waiting for %s.\n",
      static_cast<unsigned>(actualWidth),
      static_cast<unsigned>(actualHeight),
      frameSizeName(requestedFrameSize)
    );
    esp_camera_fb_return(fb);
    delay(120);
    yield();
  }

  Serial.printf(
    "Timed out waiting for %s frame after discarding %d mismatched frame(s).\n",
    frameSizeName(requestedFrameSize),
    mismatchedFrames
  );
  return nullptr;
}

static void sendCorsHeaders() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
  server.sendHeader("Cache-Control", "no-store");
}

static void handleOptions() {
  sendCorsHeaders();
  server.send(204);
}

static void handleRoot() {
  sendCorsHeaders();
  server.send(200, "text/html",
    "<!doctype html><html><head><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>ESP32-S3 Camera</title></head><body>"
    "<h1>ESP32-S3 Wi-Fi Camera</h1>"
    "<p><a href=\"/capture\">Capture VGA JPEG</a> | <a href=\"/capture?size=max\">Capture Max JPEG</a> | <a href=\"/status\">Status JSON</a> | <a href=\"/stream\">MJPEG Stream</a></p>"
    "<p><a href=\"/preset?name=bright-mat\">Bright Mat Preset</a> | <a href=\"/preset?name=default\">Default Preset</a></p>"
    "<img id=\"preview\" alt=\"Camera preview\" style=\"max-width:100%;height:auto\" />"
    "<script>"
    "const img=document.getElementById('preview');"
    "function refresh(){img.src='/capture?t='+Date.now();}"
    "img.onload=()=>setTimeout(refresh,1500);"
    "img.onerror=()=>setTimeout(refresh,3000);"
    "refresh();"
    "</script>"
    "</body></html>");
}

static void handleStatus() {
  sensor_t *sensor = esp_camera_sensor_get();
  framesize_t currentFrameSize = DEFAULT_FRAME_SIZE;
  framesize_t maxFrameSize = DEFAULT_FRAME_SIZE;
  bool hasKnownMax = false;
  uint16_t pid = 0;

  if (sensor) {
    pid = sensor->id.PID;
    currentFrameSize = sensor->status.framesize;
    hasKnownMax = sensorMaxFrameSize(pid, maxFrameSize);
  }

  sendCorsHeaders();
  String payload = "{";
  payload += "\"name\":\"" CAMERA_NAME "\",";
  payload += "\"mode\":\"";
  payload += WiFi.getMode() == WIFI_AP ? "ap" : "station";
  payload += "\",";
  payload += "\"ip\":\"";
  payload += WiFi.getMode() == WIFI_AP ? WiFi.softAPIP().toString() : WiFi.localIP().toString();
  payload += "\",";
  payload += "\"rssi\":";
  payload += WiFi.getMode() == WIFI_AP ? 0 : WiFi.RSSI();
  payload += ",";
  payload += "\"psram\":";
  payload += psramFound() ? "true" : "false";
  payload += ",";
  payload += "\"freeHeap\":";
  payload += ESP.getFreeHeap();
  payload += ",";
  payload += "\"sensorPid\":";
  payload += pid;
  payload += ",";
  payload += "\"sensorPidHex\":\"0x";
  payload += String(pid, HEX);
  payload += "\",";
  payload += "\"sensorName\":\"";
  payload += sensorName(pid);
  payload += "\",";
  appendFrameSizeJson(payload, "defaultFrameSize", DEFAULT_FRAME_SIZE);
  payload += ",";
  appendFrameSizeJson(payload, "currentFrameSize", currentFrameSize);
  payload += ",";
  if (hasKnownMax) {
    appendFrameSizeJson(payload, "maxFrameSize", maxFrameSize);
  } else {
    payload += "\"maxFrameSize\":null";
  }
  payload += ",";
  payload += "\"captureSizes\":[\"default\",\"vga\",\"svga\",\"xga\",\"sxga\",\"uxga\",\"qxga\",\"max\"]";
  payload += ",";
  appendSensorStatusJson(payload, sensor);
  payload += "}";
  server.send(200, "application/json", payload);
}

static void handleControl() {
  sendCorsHeaders();
  if (!server.hasArg("var")) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"Missing var.\"}");
    return;
  }
  if (!server.hasArg("value") && !server.hasArg("val")) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"Missing value.\"}");
    return;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  const String variable = server.arg("var");
  const int value = (server.hasArg("value") ? server.arg("value") : server.arg("val")).toInt();
  String message;
  const bool ok = applySensorControl(sensor, variable, value, message);

  String payload = "{\"ok\":";
  payload += ok ? "true" : "false";
  payload += ",\"message\":\"";
  payload += message;
  payload += "\",\"var\":\"";
  payload += variable;
  payload += "\",\"value\":";
  payload += value;
  payload += ",";
  appendSensorStatusJson(payload, sensor);
  payload += "}";
  server.send(ok ? 200 : 400, "application/json", payload);
}

static void handlePreset() {
  sendCorsHeaders();
  String preset = server.arg("name");
  preset.trim();
  preset.toLowerCase();
  preset.replace("_", "-");
  if (preset.length() == 0) preset = "default";

  sensor_t *sensor = esp_camera_sensor_get();
  String message;
  bool ok = false;
  if (preset == "default") {
    ok = applyDefaultPreset(sensor, message);
  } else if (preset == "bright-mat" || preset == "bright") {
    ok = applyBrightMatPreset(sensor, message);
  } else {
    message = "Unsupported preset";
  }

  String payload = "{\"ok\":";
  payload += ok ? "true" : "false";
  payload += ",\"message\":\"";
  payload += message;
  payload += "\",\"preset\":\"";
  payload += preset;
  payload += "\",";
  appendSensorStatusJson(payload, sensor);
  payload += "}";
  server.send(ok ? 200 : 400, "application/json", payload);
}

static bool writeAll(WiFiClient &client, const uint8_t *buffer, size_t length) {
  size_t offset = 0;
  unsigned long deadline = millis() + 15000;

  while (offset < length && client.connected()) {
    if (millis() > deadline) {
      return false;
    }

    const size_t chunk = min(static_cast<size_t>(1460), length - offset);
    const size_t written = client.write(buffer + offset, chunk);
    if (written == 0) {
      delay(1);
      yield();
      continue;
    }

    offset += written;
    deadline = millis() + 15000;
    yield();
  }

  return offset == length;
}

static void handleCapture() {
  sensor_t *sensor = esp_camera_sensor_get();
  framesize_t requestedFrameSize = DEFAULT_FRAME_SIZE;
  const String requestedSize = server.arg("size");

  if (!parseFrameSize(requestedSize, sensor, requestedFrameSize)) {
    sendCorsHeaders();
    server.send(400, "text/plain", "Unsupported capture size. Try default, vga, svga, xga, sxga, uxga, qxga, or max.");
    return;
  }

  if (!setCameraFrameSize(sensor, requestedFrameSize)) {
    sendCorsHeaders();
    server.send(503, "text/plain", "Camera failed to switch capture size");
    return;
  }

  camera_fb_t *fb = captureFrame(requestedFrameSize);
  if (!fb) {
    setCameraFrameSize(sensor, DEFAULT_FRAME_SIZE);
    sendCorsHeaders();
    server.send(503, "text/plain", "Camera failed to produce the requested capture size");
    return;
  }

  uint16_t actualWidth = 0;
  uint16_t actualHeight = 0;
  frameBufferDimensions(fb, actualWidth, actualHeight);
  WiFiClient client = server.client();
  client.setNoDelay(true);
  client.print("HTTP/1.1 200 OK\r\n");
  client.print("Access-Control-Allow-Origin: *\r\n");
  client.print("Cache-Control: no-store\r\n");
  client.print("Content-Type: image/jpeg\r\n");
  client.printf("X-Camera-Requested-Frame-Size: %s\r\n", frameSizeName(requestedFrameSize));
  client.printf("X-Camera-Frame-Width: %u\r\n", static_cast<unsigned>(actualWidth));
  client.printf("X-Camera-Frame-Height: %u\r\n", static_cast<unsigned>(actualHeight));
  client.printf("X-Camera-Sensor: %s\r\n", sensor ? sensorName(sensor->id.PID) : "unknown");
  client.printf("Content-Disposition: inline; filename=capture-%s.jpg\r\n", frameSizeName(requestedFrameSize));
  client.print("Connection: close\r\n");
  client.printf("Content-Length: %u\r\n\r\n", static_cast<unsigned>(fb->len));

  const bool complete = writeAll(client, fb->buf, fb->len);
  if (!complete) {
    Serial.println("Capture response closed before full JPEG was written.");
  }
  client.flush();
  client.stop();
  esp_camera_fb_return(fb);

  if (requestedFrameSize != DEFAULT_FRAME_SIZE && !setCameraFrameSize(sensor, DEFAULT_FRAME_SIZE)) {
    Serial.println("Failed to restore default VGA frame size after high-resolution capture.");
  }
}

static void handleStream() {
  WiFiClient client = server.client();
  const unsigned long streamDeadline = millis() + 8000;
  int framesSent = 0;
  client.print("HTTP/1.1 200 OK\r\n");
  client.print("Access-Control-Allow-Origin: *\r\n");
  client.print("Cache-Control: no-store\r\n");
  client.print("Connection: close\r\n");
  client.print("Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n");

  while (client.connected() && millis() < streamDeadline && framesSent < 3) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      delay(100);
      continue;
    }

    client.print("--frame\r\n");
    client.print("Content-Type: image/jpeg\r\n");
    client.printf("Content-Length: %u\r\n\r\n", static_cast<unsigned>(fb->len));
    const bool complete = writeAll(client, fb->buf, fb->len);
    esp_camera_fb_return(fb);
    if (!complete) {
      Serial.println("Stream response closed before full JPEG was written.");
      break;
    }
    client.print("\r\n");
    framesSent += 1;
    delay(80);
  }
  client.print("--frame--\r\n");
  client.flush();
  client.stop();
}

static bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = psramFound() ? INITIAL_PSRAM_FRAME_SIZE : DEFAULT_FRAME_SIZE;
  config.jpeg_quality = 12;
  config.fb_count = psramFound() ? 2 : 1;
  config.grab_mode = psramFound() ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor) {
    sensor->set_vflip(sensor, 1);
    sensor->set_brightness(sensor, 1);
    sensor->set_saturation(sensor, 0);
    if (!setCameraFrameSize(sensor, DEFAULT_FRAME_SIZE)) {
      return false;
    }
  }
  return true;
}

static bool connectStation() {
  if (String(WIFI_SSID).length() == 0) return false;

  WiFi.mode(WIFI_STA);
  WiFi.setHostname(CAMERA_NAME);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Joining Wi-Fi");
  for (int attempt = 0; attempt < 40; attempt += 1) {
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println();
      return true;
    }
    Serial.print(".");
    delay(500);
  }
  Serial.println();
  return false;
}

static void startFallbackAccessPoint() {
  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  WiFi.softAP(AP_SSID, AP_PASSWORD);
}

static IPAddress cameraIp() {
  return WiFi.getMode() == WIFI_AP ? WiFi.softAPIP() : WiFi.localIP();
}

static void printEndpoints() {
  IPAddress ip = cameraIp();
  Serial.println("ESP32-S3 camera ready");
  Serial.print("Mode: ");
  Serial.println(WiFi.getMode() == WIFI_AP ? "fallback access point" : "station");
  Serial.print("Base URL: http://");
  Serial.println(ip);
  Serial.print("Capture: http://");
  Serial.print(ip);
  Serial.println("/capture");
  Serial.print("Stream: http://");
  Serial.print(ip);
  Serial.println("/stream");
  Serial.print("Status: http://");
  Serial.print(ip);
  Serial.println("/status");
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  delay(1000);
  Serial.println();
  Serial.println("Booting RPG Map Projector ESP32-S3 Wi-Fi camera");

  if (!initCamera()) {
    Serial.println("Camera unavailable; halting.");
    return;
  }

  if (!connectStation()) {
    Serial.println("Wi-Fi station failed or not configured; starting fallback AP.");
    startFallbackAccessPoint();
  }

  if (MDNS.begin(CAMERA_NAME)) {
    MDNS.addService("http", "tcp", 80);
  }

  server.on("/", HTTP_GET, handleRoot);
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/stream", HTTP_GET, handleStream);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/control", HTTP_GET, handleControl);
  server.on("/preset", HTTP_GET, handlePreset);
  server.onNotFound([]() {
    if (server.method() == HTTP_OPTIONS) {
      handleOptions();
      return;
    }
    sendCorsHeaders();
    server.send(404, "text/plain", "Not found");
  });
  server.begin();
  printEndpoints();
}

void loop() {
  server.handleClient();
}
