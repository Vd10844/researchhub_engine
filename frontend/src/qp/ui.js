// src/qp/ui.js — QuickPlot primitives: API client, icons, formatting, shared components.
// No-build (Babel in the browser); every module publishes onto `window` at the bottom.

const { useState, useEffect, useRef, useCallback, useMemo } = React;

// ------------------------------------------------------------------ api client
// One place that knows about the tenant + actor headers. When auth lands, the token goes
// here and nothing else in the UI changes.
const QP = {
  org: localStorage.getItem("qp.org") || "default",
  actor: localStorage.getItem("qp.actor") || "Owen Ranford",
};

async function api(path, opts = {}) {
  const headers = { "X-Org-Id": QP.org, "X-Actor": QP.actor, ...(opts.headers || {}) };
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }
  const r = await fetch("/api/v2" + path, { ...opts, headers });
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_e) { data = { detail: text }; }
  if (!r.ok) throw new Error((data && (data.detail || data.message)) || `HTTP ${r.status}`);
  return data;
}

const fileUrl = (orderId, docId, download) =>
  `/api/v2/orders/${orderId}/documents/${docId}/file` + (download ? "?download=1" : "");

// ------------------------------------------------------------------ formatting
const fmtBytes = (n) => {
  if (!n) return "0 KB";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return Math.round(n / 1024) + " KB";
  return (n / 1048576).toFixed(1) + " MB";
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
};
const fmtTime = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  let h = d.getHours(); const m = String(d.getMinutes()).padStart(2, "0");
  const ap = h >= 12 ? "pm" : "am"; h = h % 12 || 12;
  return `${String(h).padStart(2, "0")}:${m} ${ap}`;
};
const fmtStamp = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};
const fmtNum = (n) => (n === null || n === undefined || n === "") ? "—" : Number(n).toLocaleString();
const initials = (name) => (name || "?").trim().split(/\s+/).slice(0, 2).map(s => s[0]).join("").toUpperCase();
const cx = (...a) => a.filter(Boolean).join(" ");
const extOf = (fn) => (String(fn).split(".").pop() || "").toLowerCase();
const fileKind = (fn) => {
  const e = extOf(fn);
  if (e === "pdf") return "pdf";
  if (["png", "jpg", "jpeg", "gif", "webp", "tif", "tiff"].includes(e)) return "img";
  return "doc";
};

// ---------------------------------------------------------------------- icons
const I = ({ d, size = 18, sw = 1.8, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" className={className}>{d}</svg>
);
const ic = {
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8" /></>,
  clipboard: <><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /></>,
  headset: <><path d="M3 14v-3a9 9 0 0 1 18 0v3" /><path d="M21 16a2 2 0 0 1-2 2h-1v-6h1a2 2 0 0 1 2 2ZM3 16a2 2 0 0 0 2 2h1v-6H5a2 2 0 0 0-2 2Z" /></>,
  dollar: <><path d="M12 2v20" /><path d="M17 6.5C17 4.6 14.8 3.5 12 3.5S7 4.6 7 6.5s2.2 2.8 5 3.5 5 1.6 5 3.5-2.2 3-5 3-5-1.1-5-3" /></>,
  bell: <><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></>,
  back: <path d="m15 18-6-6 6-6" />,
  chevR: <path d="m9 18 6-6-6-6" />,
  chevD: <path d="m6 9 6 6 6-6" />,
  pencil: <><path d="M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18" /></>,
  briefcase: <><rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" /></>,
  pin: <><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" /><circle cx="12" cy="10" r="3" /></>,
  columns: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>,
  frame: <><path d="M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  doc: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /></>,
  folder: <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.6 3.9A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />,
  lock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
  unlock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 7.5-2" /></>,
  download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4" /><path d="M4 21h16" /></>,
  upload: <><path d="M12 15V3m0 0 4 4m-4-4L8 7" /><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></>,
  trash: <><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6" /><path d="M10 11v6M14 11v6" /></>,
  refresh: <><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 4v5h-5" /></>,
  sparkle: <><path d="M12 3.5 13.6 8l4.4 1.6L13.6 11 12 15.5 10.4 11 6 9.6 10.4 8 12 3.5Z" /><path d="M18.5 15.5 19.3 18l2.2.8-2.2.8-.8 2.4-.8-2.4L15.5 19l2.2-.8.8-2.7Z" /></>,
  external: <><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></>,
  list: <><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>,
  check: <path d="M20 6 9 17l-5-5" />,
  x: <path d="M18 6 6 18M6 6l12 12" />,
  alert: <><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></>,
  info: <><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></>,
  loader: <><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /></>,
};

// ----------------------------------------------------------------- components
const Btn = ({ variant = "default", size, block, icon, children, className, ...rest }) => (
  <button className={cx("qp-btn", variant !== "default" && `qp-btn--${variant}`,
                        size === "sm" && "qp-btn--sm", !children && "qp-btn--icon",
                        block && "qp-btn--block", className)} {...rest}>
    {icon}{children}
  </button>
);

const Chip = ({ tone = "plain", dot, children }) => (
  <span className={cx("qp-chip", `qp-chip--${tone}`)}>
    {dot && <span className="qp-dot" />}{children}
  </span>
);

const Spinner = ({ size = 16 }) => <I d={ic.loader} size={size} className="spin" />;

const Modal = ({ open, onClose, wide, center, title, children, footer, hideClose }) => {
  useEffect(() => {
    if (!open) return;
    const h = (e) => { if (e.key === "Escape") onClose && onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="qp-modal-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose && onClose()}>
      <div className={cx("qp-modal", wide && "qp-modal--wide", center && "qp-modal--center")}>
        {title && (
          <div className="qp-modal__head">
            <div className="row between gap16">
              <h2 className="qp-h2">{title}</h2>
              {!hideClose && <Btn variant="ghost" onClick={onClose} aria-label="Close"><I d={ic.x} /></Btn>}
            </div>
          </div>
        )}
        <div className="qp-modal__body">{children}</div>
        {footer && <div className="qp-modal__foot">{footer}</div>}
      </div>
    </div>
  );
};

const Drawer = ({ open, onClose, title, children }) => {
  useEffect(() => {
    if (!open) return;
    const h = (e) => { if (e.key === "Escape") onClose && onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="qp-drawer-scrim" onClick={onClose} />
      <div className="qp-drawer">
        <div className="qp-drawer__head">
          <h2 className="qp-h2">{title}</h2>
          <Btn variant="ghost" onClick={onClose} aria-label="Close"><I d={ic.x} /></Btn>
        </div>
        <div className="qp-drawer__body scroll">{children}</div>
      </div>
    </>
  );
};

// Toasts — the only global side-channel. Kept tiny on purpose.
const _toastBus = { push: null };
const toast = (msg, kind) => _toastBus.push && _toastBus.push(msg, kind);

const Toasts = () => {
  const [items, setItems] = useState([]);
  useEffect(() => {
    _toastBus.push = (msg, kind) => {
      const id = Math.random().toString(36).slice(2);
      setItems((x) => [...x, { id, msg, kind }]);
      setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), kind === "err" ? 7000 : 4000);
    };
    return () => { _toastBus.push = null; };
  }, []);
  return (
    <div className="qp-toast-wrap">
      {items.map((t) => (
        <div key={t.id} className={cx("qp-toast", t.kind === "err" && "qp-toast--err")}>
          <I d={t.kind === "err" ? ic.alert : ic.check} size={16} />
          <span>{t.msg}</span>
        </div>
      ))}
    </div>
  );
};

// A small hook for "load this, show a spinner, surface the error".
function useAsync(fn, deps, { auto = true } = {}) {
  const [state, setState] = useState({ data: null, loading: auto, error: "" });
  const run = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const data = await fn();
      setState({ data, loading: false, error: "" });
      return data;
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: e.message }));
      throw e;
    }
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (auto) run().catch(() => {}); }, [run, auto]);
  return { ...state, run, set: (d) => setState((s) => ({ ...s, data: d })) };
}

// Static map thumbnail — free Esri World Imagery, no key. Falls back to a grey tile.
const _merc = (lon, lat) => {
  const x = lon * 20037508.342789244 / 180;
  const y = Math.log(Math.tan((90 + lat) * Math.PI / 360)) / (Math.PI / 180)
            * 20037508.342789244 / 180;
  return [x, y];
};
const MapThumb = ({ lat, lon, w = 96, h = 72, half = 190, className }) => {
  if (lat == null || lon == null) {
    return <div className={cx("qp-map", className)} style={{ width: w, height: h }} />;
  }
  const [cx0, cy0] = _merc(lon, lat);
  const bbox = `${cx0 - half},${cy0 - half},${cx0 + half},${cy0 + half}`;
  const src = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?"
    + new URLSearchParams({ bbox, bboxSR: "3857", imageSR: "3857",
                            size: `${w * 2},${h * 2}`, format: "png32", f: "image" });
  return <img src={src} alt="" width={w} height={h} className={cx("qp-map", className)} loading="lazy" />;
};

const FileIcon = ({ name }) => {
  const kind = fileKind(name);
  return (
    <span className={cx("qp-fileicon", `qp-fileicon--${kind}`)}>
      {kind === "pdf" ? "PDF" : kind === "img" ? "IMG" : extOf(name).slice(0, 3).toUpperCase() || "FILE"}
    </span>
  );
};

// Search box with a one-click clear. Escape clears too — that is what people reach for
// first, and having to hold backspace is a small daily irritation.
const SearchInput = ({ value, onChange, placeholder = "Search", width, autoFocus }) => {
  const ref = useRef(null);
  const clear = () => { onChange(""); ref.current && ref.current.focus(); };
  return (
    <div className="qp-search" style={width ? { width } : undefined}>
      <I d={ic.search} size={17} className="qp-search__icon" />
      <input
        ref={ref}
        className="qp-input"
        type="search"
        placeholder={placeholder}
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Escape" && value) { e.preventDefault(); clear(); } }}
      />
      {value && (
        <button type="button" className="qp-search__clear" onClick={clear}
                aria-label="Clear search" title="Clear search (Esc)">
          <I d={ic.x} size={15} sw={2.2} />
        </button>
      )}
    </div>
  );
};

// Debounce a fast-changing value (search boxes) so we do not fire a request per keystroke.
function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

const Empty = ({ icon, title, text, children }) => (
  <div className="qp-empty">
    <div className="qp-empty__icon">{icon || <I d={ic.folder} size={26} />}</div>
    <div className="qp-empty__title">{title}</div>
    {text && <p className="qp-empty__text">{text}</p>}
    {children && <div className="mt20 row gap12" style={{ justifyContent: "center" }}>{children}</div>}
  </div>
);

Object.assign(window, {
  useState, useEffect, useRef, useCallback, useMemo,
  QP, api, fileUrl,
  fmtBytes, fmtDate, fmtTime, fmtStamp, fmtNum, initials, cx, extOf, fileKind,
  I, ic, Btn, Chip, Spinner, Modal, Drawer, Toasts, toast, useAsync, MapThumb, FileIcon, Empty,
  SearchInput, useDebounced,
});
