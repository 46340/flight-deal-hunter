// Leaflet map: clustered airport markers, radius circles, highlighted selections.
// Leaflet and markercluster are classic scripts that set window.L.

import { el } from "./util.js";

export const SIDE_COLORS = { origins: "#2563eb", destinations: "#ea580c" };

export class AirportMap {
  constructor(container, { onPick }) {
    const L = window.L;
    this.L = L;
    this.onPick = onPick;
    this.map = L.map(container, { worldCopyJump: true, zoomControl: true }).setView([50, 10], 3);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 12,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(this.map);
    this.cluster = L.markerClusterGroup({ chunkedLoading: true, showCoverageOnHover: false, disableClusteringAtZoom: 8, maxClusterRadius: 45 });
    this.map.addLayer(this.cluster);
    // Selections sit above the clustered markers so they stay visible.
    this.map.createPane("selection").style.zIndex = 650;
    this.sides = {
      origins: { circle: null, layer: L.layerGroup().addTo(this.map) },
      destinations: { circle: null, layer: L.layerGroup().addTo(this.map) },
    };
  }

  setAirports(airports) {
    const L = this.L;
    this.cluster.clearLayers();
    const icon = (a) => L.divIcon({ className: a.type === "large_airport" ? "ap-dot" : "ap-dot medium", iconSize: [10, 10] });
    const markers = airports.map((a) => {
      const m = L.marker([a.lat, a.lon], { icon: icon(a), title: `${a.iata} ${a.name}` });
      m.bindPopup(() => this.popup(a));
      return m;
    });
    this.cluster.addLayers(markers);
  }

  popup(a) {
    const pick = (side) => () => {
      this.map.closePopup();
      this.onPick(side, a);
    };
    return el(
      "div",
      { class: "ap-popup" },
      el("strong", {}, `${a.iata} `),
      a.name,
      el("div", { class: "muted" }, [a.city, a.country].filter(Boolean).join(", ")),
      el(
        "div",
        { class: "popup-actions" },
        el("button", { type: "button", class: "btn small origin", onclick: pick("origins") }, "Origin center"),
        el("button", { type: "button", class: "btn small destination", onclick: pick("destinations") }, "Destination center"),
      ),
    );
  }

  /** Draw a side: circle around center and colored dots on selected (and excluded) airports. */
  setSide(side, center, radiusKm, hits, checked) {
    const L = this.L;
    const s = this.sides[side];
    const color = SIDE_COLORS[side];
    s.layer.clearLayers();
    s.circle = null;
    if (!center) return;
    s.circle = L.circle([center.lat, center.lon], { radius: radiusKm * 1000, color, weight: 2, fillOpacity: 0.06 }).addTo(s.layer);
    for (const { airport: a } of hits) {
      const on = checked.has(a.iata);
      L.circleMarker([a.lat, a.lon], {
        radius: a.iata === center.iata ? 8 : 6,
        color,
        weight: 2,
        fillColor: on ? color : "#ffffff",
        fillOpacity: on ? 0.9 : 0.6,
        interactive: false,
        pane: "selection",
      }).addTo(s.layer);
    }
  }

  fit() {
    const bounds = [];
    for (const s of Object.values(this.sides)) if (s.circle) bounds.push(s.circle.getBounds());
    if (!bounds.length) return;
    let b = bounds[0];
    for (const x of bounds.slice(1)) b = b.extend(x);
    this.map.fitBounds(b, { padding: [20, 20], maxZoom: 8 });
  }

  focus(airport, radiusKm) {
    const circle = this.L.circle([airport.lat, airport.lon], { radius: Math.max(radiusKm, 50) * 1000 });
    this.map.addLayer(circle);
    this.map.fitBounds(circle.getBounds(), { padding: [20, 20], maxZoom: 8 });
    this.map.removeLayer(circle);
  }

  refresh() {
    this.map.invalidateSize();
  }
}
