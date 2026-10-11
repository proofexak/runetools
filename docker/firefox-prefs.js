// Firefox defaults in the bot image (docker/Dockerfile → /usr/lib/firefox/defaults/pref/):
// what a Polish user's browser on an Ubuntu laptop would have, so sites see one
// consistent person behind the proxy's Polish IP.

// Polish UI (firefox-l10n-pl); its language pack sets Accept-Language /
// navigator.languages to Polish Firefox's own default, "pl, en-US, en"
pref("intl.locale.requested", "pl");

// DNS over HTTPS only: lookups go through the proxy like everything else, instead of
// the host's resolver (a DNS-leak check would otherwise show the home ISP's resolver)
pref("network.trr.mode", 3);
pref("network.trr.uri", "https://mozilla.cloudflare-dns.com/dns-query");
pref("network.trr.bootstrapAddr", "1.1.1.1");
pref("network.trr.bootstrapAddress", "1.1.1.1");

// no "make Firefox your default browser?" prompt over the page
pref("browser.shell.checkDefaultBrowser", false);
