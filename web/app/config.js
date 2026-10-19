/* Where the phone app finds the RangeIQ server.
   Served from the server itself (rangeiq.org/app/): use the same site.
   Served from GitHub Pages or anywhere else: use the RangeIQ server's API. */
window.RANGEIQ_API = /(^|\.)rangeiq\.org$/.test(location.hostname) || location.hostname === "localhost"
  ? "../api/"
  : "https://rangeiq.org/api/";
