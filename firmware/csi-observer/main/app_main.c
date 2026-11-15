/*
 * DrosoBot CSI receiver: only for an INDEPENDENT ESP32-C3 test board.
 * Does not scan, sniff promiscuously, modify the access point, transmit
 * crafted 802.11 frames, expose raw IQ values, or control the robot.
 *
 * CSI is the channel response to normal Wi-Fi frames sent by the currently
 * associated AP. An ICMP echo to the already-associated default gateway at
 * 1 Hz stimulates router replies without changing its radio configuration.
 *
 * IMPORTANT: CSI RX callback is a Wi-Fi high-priority task: queue only.
 * A separate lower-priority task emits anonymized summaries to UART.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/event_groups.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "ping/ping_sock.h"
#include "lwip/ip4_addr.h"

#define CSI_BUF_LIMIT 256
#define CSI_BUCKETS 8
#define WIFI_CONNECTED_BIT BIT0
#define CSI_QUEUE_LEN 24

static EventGroupHandle_t s_connected;
static QueueHandle_t s_queue;
static uint8_t s_associated_bssid[6];
static volatile uint32_t s_queue_drops=0;
static volatile bool s_stopping=false;
static int s_connect_attempts=0;
static esp_ping_handle_t s_ping=NULL;

typedef struct {
    uint16_t len;
    uint8_t first_word_invalid;
    int8_t rssi;
    int8_t iq[CSI_BUF_LIMIT];
} csi_frame_t;

/* Never use IP, MAC, SSID or packet payload in the public UART record. */
static void csi_callback(void *ctx, wifi_csi_info_t *info) {
    (void)ctx;
    if (s_stopping || !info || !info->buf || !s_queue ||
        memcmp(info->mac, s_associated_bssid, sizeof(s_associated_bssid)) != 0 ||
        info->len < 16 || info->len > CSI_BUF_LIMIT) {
        return;
    }
    csi_frame_t frame={0};
    frame.len=info->len;
    frame.first_word_invalid=info->first_word_invalid;
    frame.rssi=info->rx_ctrl.rssi;
    memcpy(frame.iq, info->buf, info->len);
    if (xQueueSend(s_queue,&frame,0)!=pdTRUE) {
        s_queue_drops++;
    }
}

static void wifi_event(void *arg,esp_event_base_t base,int32_t id,void *data) {
    (void)arg;(void)data;
    if (base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_connected,WIFI_CONNECTED_BIT);
        if (!s_stopping && ++s_connect_attempts<=4) esp_wifi_connect();
    } else if (base==IP_EVENT && id==IP_EVENT_STA_GOT_IP) {
        s_connect_attempts=0;
        xEventGroupSetBits(s_connected,WIFI_CONNECTED_BIT);
    }
}

static void publish_summary(uint32_t start_ms,uint32_t frames,uint32_t queue_drops,
                            int64_t rssi_sum,uint64_t buckets[CSI_BUCKETS],
                            uint32_t bucket_counts[CSI_BUCKETS]) {
    if (frames==0) {
        printf("CSI1,%lu,0,%lu,0,0,0,0,0,0,0,0,0\n",
               (unsigned long)start_ms,(unsigned long)queue_drops);
        return;
    }
    printf("CSI1,%lu,%lu,%lu,%ld", (unsigned long)start_ms,
           (unsigned long)frames,(unsigned long)queue_drops,
           (long)(rssi_sum/(int64_t)frames));
    for (int b=0;b<CSI_BUCKETS;b++) {
        const uint64_t mean=bucket_counts[b]?buckets[b]/bucket_counts[b]:0;
        printf(",%lu",(unsigned long)mean);
    }
    printf("\n");
}

static void analyzer(void *arg) {
    (void)arg;
    uint32_t frames=0;
    int64_t rssi_sum=0;
    uint64_t bucket_sums[CSI_BUCKETS]={0};
    uint32_t bucket_counts[CSI_BUCKETS]={0};
    uint32_t last_drops=0;
    uint32_t last_ms=(uint32_t)(esp_timer_get_time()/1000);
    csi_frame_t frame;
    for (uint32_t window=0; window<CONFIG_DROSOBOT_CSI_MAX_WINDOWS; ) {
        if (xQueueReceive(s_queue,&frame,pdMS_TO_TICKS(100))==pdTRUE) {
            const int begin=frame.first_word_invalid?4:0;
            if (frame.len>(uint16_t)(begin+12)) {
                frames++;
                rssi_sum+=frame.rssi;
                const int pairs=(frame.len-begin)/2;
                for (int j=0;j<pairs;j++) {
                    const int im=frame.iq[begin+j*2];
                    const int re=frame.iq[begin+j*2+1];
                    const uint32_t magnitude_sq=(uint32_t)(im*im+re*re);
                    const int bucket=(j*CSI_BUCKETS)/pairs;
                    bucket_sums[bucket]+=magnitude_sq;
                    bucket_counts[bucket]++;
                }
            }
        }
        const uint32_t now=(uint32_t)(esp_timer_get_time()/1000);
        if ((uint32_t)(now-last_ms)>=1000) {
            const uint32_t drops=s_queue_drops;
            publish_summary(now,frames,drops-last_drops,rssi_sum,bucket_sums,bucket_counts);
            last_drops=drops;
            frames=0;rssi_sum=0;
            memset(bucket_sums,0,sizeof(bucket_sums));
            memset(bucket_counts,0,sizeof(bucket_counts));
            last_ms=now;
            window++;
        }
    }
    s_stopping=true;
    if (s_ping) {
        esp_ping_stop(s_ping);
        esp_ping_delete_session(s_ping);
        s_ping=NULL;
    }
    esp_wifi_set_csi(false);
    esp_wifi_set_csi_rx_cb(NULL,NULL);
    esp_wifi_stop();
    puts("CSI_OBSERVER_COMPLETE: radio stopped after bounded capture");
    vTaskDelete(NULL);
}

static void start_gateway_pings(void) {
    esp_netif_ip_info_t details;
    esp_netif_t *sta=esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    ESP_ERROR_CHECK(esp_netif_get_ip_info(sta,&details));
    esp_ping_config_t config=ESP_PING_DEFAULT_CONFIG();
    config.count=0; /* limited by firmware task lifetime; <= 1 per second */
    config.interval_ms=CONFIG_DROSOBOT_CSI_PING_INTERVAL_MS;
    config.timeout_ms=500;
    config.data_size=8;
    config.target_addr.type=ESP_IPADDR_TYPE_V4;
    config.target_addr.u_addr.ip4.addr=ip4_addr_get_u32(&details.gw);
    esp_ping_callbacks_t callbacks={0};
    ESP_ERROR_CHECK(esp_ping_new_session(&config,&callbacks,&s_ping));
    ESP_ERROR_CHECK(esp_ping_start(s_ping));
}

void app_main(void) {
    if (strcmp(CONFIG_DROSOBOT_CSI_SSID,"DROSOBOT_UNCONFIGURED")==0 ||
        strlen(CONFIG_DROSOBOT_CSI_SSID)==0) {
        puts("CSI_OBSERVER_UNCONFIGURED: configure authorized SSID on dedicated test board; no radio started");
        return;
    }
    s_queue=xQueueCreate(CSI_QUEUE_LEN,sizeof(csi_frame_t));
    s_connected=xEventGroupCreate();
    if (!s_queue || !s_connected) {puts("CSI_OBSERVER_ALLOC_FAILED");return;}
    esp_err_t err=nvs_flash_init();
    if (err==ESP_ERR_NVS_NO_FREE_PAGES || err==ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());err=nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t wifi_cfg=WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_cfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,&wifi_event,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,&wifi_event,NULL));
    wifi_config_t wifi={0};
    /* SSID/password stay in a LOCAL untracked sdkconfig; never logs these. */
    strncpy((char*)wifi.sta.ssid,CONFIG_DROSOBOT_CSI_SSID,sizeof(wifi.sta.ssid));
    strncpy((char*)wifi.sta.password,CONFIG_DROSOBOT_CSI_PASSWORD,sizeof(wifi.sta.password));
    wifi.sta.pmf_cfg.capable=true;
    wifi.sta.pmf_cfg.required=false;
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA,&wifi));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_connect());
    if (!(xEventGroupWaitBits(s_connected,WIFI_CONNECTED_BIT,pdFALSE,pdFALSE,
                               pdMS_TO_TICKS(20000))&WIFI_CONNECTED_BIT)) {
        puts("CSI_OBSERVER_STA_CONNECTION_FAILED");return;
    }
    wifi_ap_record_t ap={0};
    ESP_ERROR_CHECK(esp_wifi_sta_get_ap_info(&ap));
    memcpy(s_associated_bssid,ap.bssid,sizeof(s_associated_bssid));
    wifi_csi_config_t csi={
        .lltf_en=true,.htltf_en=false,.stbc_htltf2_en=false,
        .ltf_merge_en=false,.channel_filter_en=false,
        .manu_scale=false,.shift=0
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_callback,NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
    xTaskCreate(analyzer,"csi_features",4096,NULL,4,NULL);
    start_gateway_pings();
    printf("CSI_OBSERVER_STARTED: associated AP only; CSI1 UART summaries, max_windows=%d\n",
           CONFIG_DROSOBOT_CSI_MAX_WINDOWS);
}
