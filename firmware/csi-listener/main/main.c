/*
 * CSI experiment for a DEDICATED standalone ESP32-C3, not ESP-Hi firmware.
 * Receive-only channel monitor: no association, credentials, frame payloads,
 * source/destination MACs, packet injection, channel hopping, or Tenda changes.
 * Derived aggregate metrics on UART; never exports raw CSI/complex samples.
 * Target ESP-IDF 5.5 ESP32-C3; build and flash are separate manual steps.
 */
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#define CSI_MAX_BYTES 512
#define CSI_QUEUE_DEPTH 12
#define CSI_SAMPLE_INTERVAL_US 20000LL /* at most 50 samples/sec */
#define CSI_AGGREGATION_WINDOW_MS 1000

static const char *TAG = "drosobot_csi";

typedef struct {
    uint16_t len;
    uint8_t invalid_first;
    int8_t rssi;
    int8_t noise_floor;
    int8_t bytes[CSI_MAX_BYTES];
} csi_sample_t;

static QueueHandle_t sample_queue;
static volatile uint32_t dropped_overload;
static volatile uint32_t dropped_size;
static volatile uint32_t skipped_rate;
static int64_t last_queued_us;

static void on_csi(void *context, wifi_csi_info_t *info) {
    (void)context;
    if (info == NULL || info->buf == NULL || info->len < 8) return;
    if (info->len > CSI_MAX_BYTES || (info->len & 1U)) {
        dropped_size++;
        return;
    }
    const int64_t now = esp_timer_get_time();
    if (now - last_queued_us < CSI_SAMPLE_INTERVAL_US) {
        skipped_rate++;
        return;
    }
    last_queued_us = now;
    csi_sample_t s = { 0 };
    s.len = info->len;
    s.invalid_first = info->first_word_invalid ? 1 : 0;
    s.rssi = info->rx_ctrl.rssi;
    s.noise_floor = info->rx_ctrl.noise_floor;
    memcpy(s.bytes, info->buf, info->len);
    if (xQueueSend(sample_queue, &s, 0) != pdTRUE) dropped_overload++;
    /* Intentionally never access info->mac or info->payload. */
}

typedef struct {
    uint32_t frames;
    double rssi_sum;
    double noise_sum;
    double mean_power_sum;
    double profile_delta_sum;
    uint32_t comparable_profiles;
    uint16_t prior_pairs;
    uint16_t prior_skip;
    double prior_normalized[CSI_MAX_BYTES / 2];
} window_t;

static void update_window(window_t *w, const csi_sample_t *s) {
    const uint16_t n = s->len / 2;
    const uint16_t skip = s->invalid_first ? 2 : 0; /* ESP32-C3 first 4 bytes invalid */
    if (n <= skip) return;
    double power_sum = 0.0;
    double powers[CSI_MAX_BYTES / 2];
    for (uint16_t i = skip; i < n; ++i) {
        /* Documented byte order is imaginary first, real second. */
        const int32_t im = s->bytes[2 * i];
        const int32_t re = s->bytes[2 * i + 1];
        powers[i] = (double)(im * im + re * re);
        power_sum += powers[i];
    }
    const double mean_power = power_sum / (n - skip);
    if (mean_power <= 0.0) return;
    double delta = 0.0;
    for (uint16_t i = skip; i < n; ++i) {
        const double normalized = powers[i] / mean_power;
        if (w->prior_pairs == n && w->prior_skip == skip)
            delta += fabs(normalized - w->prior_normalized[i]);
        w->prior_normalized[i] = normalized;
    }
    if (w->prior_pairs == n && w->prior_skip == skip) {
        w->comparable_profiles++;
        w->profile_delta_sum += delta / (n - skip);
    }
    w->prior_pairs = n;
    w->prior_skip = skip;
    w->frames++;
    w->rssi_sum += s->rssi;
    w->noise_sum += s->noise_floor;
    w->mean_power_sum += mean_power;
}

static void output_window(uint32_t sequence, const window_t *window) {
    const double denom = window->frames ? window->frames : 1;
    const double comparisons = window->comparable_profiles ? window->comparable_profiles : 1;
    /* Aggregate-only CSV. No MACs, SSIDs, CSI buffers, packet payload or location. */
    printf("CSI_AGG_V1,%lu,%lld,%d,%lu,%lu,%lu,%lu,%.3f,%.3f,%.3f,%.6f\n",
           (unsigned long)sequence, (long long)(esp_timer_get_time() / 1000),
           CONFIG_DROSOBOT_CSI_CHANNEL, (unsigned long)window->frames,
           (unsigned long)dropped_overload, (unsigned long)dropped_size,
           (unsigned long)skipped_rate,
           window->rssi_sum / denom, window->noise_sum / denom,
           window->mean_power_sum / denom,
           window->profile_delta_sum / comparisons);
    fflush(stdout);
}

void app_main(void) {
    /* Never erase existing NVS on errors. Do not reuse a provisioned robot. */
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    sample_queue = xQueueCreate(CSI_QUEUE_DEPTH, sizeof(csi_sample_t));
    if (!sample_queue) {
        ESP_LOGE(TAG, "sample queue unavailable");
        return;
    }
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_channel(CONFIG_DROSOBOT_CSI_CHANNEL, WIFI_SECOND_CHAN_NONE));
    wifi_promiscuous_filter_t filter = { .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT };
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));
    wifi_csi_config_t csi = {
        .lltf_en = true, .htltf_en = true, .stbc_htltf2_en = false,
        .ltf_merge_en = true, .channel_filter_en = true,
        .manu_scale = false, .shift = 0,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(on_csi, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    printf("CSI_SESSION_V1,origin=esp32c3_live_passive,channel=%d,windows=%d\n",
           CONFIG_DROSOBOT_CSI_CHANNEL, CONFIG_DROSOBOT_CSI_MAX_WINDOWS);
    fflush(stdout);

    for (uint32_t window = 0; window < CONFIG_DROSOBOT_CSI_MAX_WINDOWS; ++window) {
        window_t aggregate = { 0 };
        const int64_t end = esp_timer_get_time() + 1000000;
        while (esp_timer_get_time() < end) {
            csi_sample_t packet;
            if (xQueueReceive(sample_queue, &packet, pdMS_TO_TICKS(40)) == pdTRUE)
                update_window(&aggregate, &packet);
        }
        output_window(window, &aggregate);
    }
    ESP_ERROR_CHECK(esp_wifi_set_csi(false));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(false));
    ESP_ERROR_CHECK(esp_wifi_stop());
    printf("CSI_COMPLETE_V1,windows=%d,radio=stopped\n", CONFIG_DROSOBOT_CSI_MAX_WINDOWS);
    fflush(stdout);
    vQueueDelete(sample_queue);
    sample_queue = NULL;
    /* Radio remains stopped until separate experiment or restart. */
}
