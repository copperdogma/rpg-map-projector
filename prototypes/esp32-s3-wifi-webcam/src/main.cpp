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
    "<p><a href=\"/capture\">Capture JPEG</a> | <a href=\"/status\">Status JSON</a> | <a href=\"/stream\">MJPEG Stream</a></p>"
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
  payload += "}";
  server.send(200, "application/json", payload);
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
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    sendCorsHeaders();
    server.send(503, "text/plain", "Camera capture failed");
    return;
  }

  WiFiClient client = server.client();
  client.setNoDelay(true);
  client.print("HTTP/1.1 200 OK\r\n");
  client.print("Access-Control-Allow-Origin: *\r\n");
  client.print("Cache-Control: no-store\r\n");
  client.print("Content-Type: image/jpeg\r\n");
  client.print("Content-Disposition: inline; filename=capture.jpg\r\n");
  client.print("Connection: close\r\n");
  client.printf("Content-Length: %u\r\n\r\n", static_cast<unsigned>(fb->len));

  const bool complete = writeAll(client, fb->buf, fb->len);
  if (!complete) {
    Serial.println("Capture response closed before full JPEG was written.");
  }
  client.flush();
  client.stop();
  esp_camera_fb_return(fb);
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
  config.frame_size = FRAMESIZE_VGA;
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
