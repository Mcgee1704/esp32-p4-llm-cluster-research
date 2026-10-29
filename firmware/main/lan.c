#include "app.h"
#include "esp_eth.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_log.h"
#include "sdkconfig.h"
volatile int lan_ready;
volatile uint32_t lan_ip4;
static esp_eth_handle_t ethernet;
void lan_stop(void) {
    if(ethernet)(void)esp_eth_stop(ethernet);
    lan_ready=0;lan_ip4=0;
}
static void link_event(void *arg,esp_event_base_t base,int32_t id,void *data) {
    (void)arg;(void)base;(void)data;
    if(id==ETHERNET_EVENT_DISCONNECTED||id==ETHERNET_EVENT_STOP){lan_ready=0;lan_ip4=0;}
}
static void address(void *arg,esp_event_base_t base,int32_t id,void *data) {
    (void)arg;(void)base;(void)id;
    ip_event_got_ip_t *e=data;
    lan_ready=1;
    lan_ip4=e->ip_info.ip.addr;
    ESP_LOGI("lan","Browser: http://" IPSTR,IP2STR(&e->ip_info.ip));
}
void lan_start(void) {
    ESP_ERROR_CHECK(esp_netif_init());ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_config_t net=ESP_NETIF_DEFAULT_ETH();
    esp_netif_t *iface=esp_netif_new(&net);assert(iface);
    ESP_ERROR_CHECK(esp_netif_set_hostname(iface,"p4-tinystories"));
    eth_mac_config_t mc=ETH_MAC_DEFAULT_CONFIG();
    eth_esp32_emac_config_t emac=ETH_ESP32_EMAC_DEFAULT_CONFIG();
    /* Waveshare schematic: MDC31 MDIO52 RXDV28 RXD0/1=29/30 TXEN49 TXD0/1=34/35 CLK50. */
    emac.smi_gpio.mdc_num=31;emac.smi_gpio.mdio_num=52;
    eth_phy_config_t pc=ETH_PHY_DEFAULT_CONFIG();
    pc.phy_addr=CONFIG_CLUSTER_PHY_ADDR;pc.reset_gpio_num=51;
    esp_eth_mac_t *mac=esp_eth_mac_new_esp32(&emac,&mc);assert(mac);
    esp_eth_phy_t *phy=esp_eth_phy_new_ip101(&pc);assert(phy);
    esp_eth_config_t ec=ETH_DEFAULT_CONFIG(mac,phy);
    ESP_ERROR_CHECK(esp_eth_driver_install(&ec,&ethernet));
    ESP_ERROR_CHECK(esp_netif_attach(iface,esp_eth_new_netif_glue(ethernet)));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_ETH_GOT_IP,address,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(ETH_EVENT,ESP_EVENT_ANY_ID,link_event,NULL));
    ESP_ERROR_CHECK(esp_eth_start(ethernet));
}
