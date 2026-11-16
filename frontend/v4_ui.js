/**
 * AI圆桌 v4/v5 — 单源显式 Store 多模态附件控制器、局部空心线性矢量徽标水合器与动态驱动目录芯片组件
 * 架构基线：
 * 1. 无全局请求拦截、无全文档 DOM 监听，全部状态统一收口至 app.js 单源显式 Store；
 * 2. 通过局部渲染钩子按需水合单张发言卡、白板区或顶栏徽章，6 席并发流式输出零全树重排；
 * 3. 模型快选芯片与推理档位胶囊完全由 /api/status 下发的单源 driver_catalog 动态渲染。
 */

export const SEAT_VECTOR_ICONS = {
  carbon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 3.5 20.5 8 12 12.5 3.5 8 12 3.5"></polygon><polyline points="3.5 12.8 12 17.2 20.5 12.8"></polyline><polyline points="5.5 17 12 20.5 18.5 17"></polyline></svg>`,
  grok: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20.8s7.2-3.6 7.2-9.2V5.4L12 2.8 4.8 5.4v6.2c0 5.6 7.2 9.2 7.2 9.2z"></path><circle cx="12" cy="11.4" r="2.5"></circle></svg>`,
  astra: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><polyline points="7.2 8.2 3.2 12 7.2 15.8"></polyline><polyline points="16.8 8.2 20.8 12 16.8 15.8"></polyline><line x1="13.6" y1="5.2" x2="10.4" y2="18.8"></line></svg>`,
  vega: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 3.2 18.2 11.8 12 20.8 5.8 11.8 12 3.2"></polygon><line x1="12" y1="3.2" x2="12" y2="10.2"></line><circle cx="12" cy="12" r="1.8"></circle></svg>`,
  titan: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polyline points="2.8 12 7.2 12 10 5 14 19 16.8 12 21.2 12"></polyline></svg>`,
  prism: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2.8 20.2 7.5 20.2 16.5 12 21.2 3.8 16.5 3.8 7.5 12 2.8"></polygon><polyline points="8.4 12.2 11 14.8 15.8 9.6"></polyline></svg>`,
  chair: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2.8 14.6 9.4 21.2 12 14.6 14.6 12 21.2 9.4 14.6 2.8 12 9.4 9.4 12 2.8"></polygon></svg>`,
  system: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.4"></circle><circle cx="12" cy="12" r="2.8"></circle></svg>`,
};

export const LINEAR_UI_ICONS = {
  paperclip: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="13.5" height="13.5" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.2 11.2l-8.8 8.8a5.8 5.8 0 0 1-8.2-8.2l8.8-8.8a3.9 3.9 0 0 1 5.5 5.5l-8.8 8.8a1.95 1.95 0 0 1-2.76-2.76l8.1-8.1"></path></svg>`,
  close: `<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="6" y1="6" x2="18" y2="18"></line><line x1="18" y1="6" x2="6" y2="18"></line></svg>`,
  adopt: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12.5" height="12.5" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"></circle><polyline points="8.4 12.2 11 14.8 15.8 9.6"></polyline></svg>`,
  discuss: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12.5" height="12.5" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8A2.5 2.5 0 0 1 17.5 17H9l-4.2 3.2V17A2.5 2.5 0 0 1 4 14.5z"></path></svg>`,
  pin: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8.5 4h7l-1.2 6.2L17.5 13H6.5l3.2-2.8z"></path><line x1="12" y1="13" x2="12" y2="20"></line></svg>`,
  edit: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 19.5l1.4-4.8L15.2 5.4a1.8 1.8 0 0 1 2.5 2.5L8.4 17.2z"></path><line x1="4.5" y1="20.5" x2="19.5" y2="20.5"></line></svg>`,
  copy: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8.5" y="8.5" width="11" height="11" rx="2.2"></rect><path d="M5.5 15.5H5a2 2 0 0 1-2-2v-8.5a2 2 0 0 1 2-2h8.5a2 2 0 0 1 2 2v.5"></path></svg>`,
};

const MODE_SHORT_LABELS = {
  deep_deliberation: "深度研讨",
  adversarial_review: "正反辩证",
  divergent_convergent: "发散收敛",
  code_review: "代码审查",
  rapid_consensus: "快速合议",
};

const SEAT_CAPS = ["Carbon", "Grok", "Astra", "Vega", "Titan", "Prism"];

const storeBridge = {
  state: null,
  authState: null,
  onUploadStateChange: null,
  initialized: false,
  dragDepth: 0,
};

const $id = (id) => document.getElementById(id);

function escapeAttr(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function notifyToast(msg, kind = "info") {
  const box = $id("toastContainer");
  if (!box) return;
  const item = document.createElement("div");
  const cls = kind === "ok" ? "toast-ok" : kind === "err" ? "toast-err" : kind === "warn" ? "toast-warn" : "";
  item.className = `toast-item ${cls}`.trim();
  item.textContent = msg;
  box.appendChild(item);
  setTimeout(() => {
    item.style.opacity = "0";
    item.style.transform = "translateY(-4px)";
    item.style.transition = "opacity 160ms ease, transform 160ms ease";
    setTimeout(() => item.remove(), 180);
  }, 2800);
}

export function bindV4StoreBridge({ state, authState, onUploadStateChange }) {
  storeBridge.state = state;
  storeBridge.authState = authState;
  storeBridge.onUploadStateChange = typeof onUploadStateChange === "function" ? onUploadStateChange : null;
  if (!Array.isArray(state.pendingAttachments)) state.pendingAttachments = [];
  if (!(state.blobUrlCache instanceof Map)) state.blobUrlCache = new Map();
  if (!(state.msgAttachmentsById instanceof Map)) state.msgAttachmentsById = new Map();
}

function getPendingAttachments() {
  return storeBridge.state?.pendingAttachments || [];
}

function setPendingAttachments(nextList) {
  if (storeBridge.state) {
    storeBridge.state.pendingAttachments = nextList;
  }
}

function getBlobCache() {
  return storeBridge.state?.blobUrlCache || new Map();
}

function getMsgAttachmentMap() {
  return storeBridge.state?.msgAttachmentsById || new Map();
}

function getCurrentSessionId() {
  return String(storeBridge.state?.currentSessionId || "");
}

function getAuthToken() {
  return String(storeBridge.authState?.token || "");
}

function emitUploadStateChanged() {
  if (storeBridge.onUploadStateChange) {
    storeBridge.onUploadStateChange();
  }
}

export function hasUploadingAttachments() {
  return getPendingAttachments().some((a) => a && a.uploading === true);
}

export function getReadyPendingAttachments(forSessionId = "") {
  const sid = forSessionId || getCurrentSessionId();
  return getPendingAttachments().filter(
    (a) => a && a.id && !a.uploading && (!a.sessionId || !sid || a.sessionId === sid)
  );
}

function isBlobReferencedInSessionMessages(blobUrl, sessionId) {
  if (!blobUrl || !blobUrl.startsWith("blob:")) return false;
  const blobCache = getBlobCache();
  const msgMap = getMsgAttachmentMap();
  for (const [, atts] of msgMap.entries()) {
    if (!Array.isArray(atts)) continue;
    for (const att of atts) {
      if (att?.id && blobCache.get(`${sessionId}:${att.id}`) === blobUrl) {
        return true;
      }
    }
  }
  return false;
}

function safeRevokeObjectUrl(url) {
  if (typeof url === "string" && url.startsWith("blob:")) {
    try {
      URL.revokeObjectURL(url);
    } catch {
      // ignore revoke errors
    }
  }
}

export function revokePendingAttachmentUrl(att, sessionId = "") {
  if (!att) return;
  const sid = sessionId || att.sessionId || getCurrentSessionId();
  const cache = getBlobCache();
  const cacheKey = sid && att.id ? `${sid}:${att.id}` : "";
  const url = att.previewUrl || (cacheKey ? cache.get(cacheKey) : "");
  if (url && !isBlobReferencedInSessionMessages(url, sid)) {
    safeRevokeObjectUrl(url);
    if (cacheKey && cache.get(cacheKey) === url) {
      cache.delete(cacheKey);
    }
  }
}

export function clearPendingAttachmentsOnSend(sentIds, sessionId) {
  const sentSet = new Set(sentIds || []);
  const kept = [];
  for (const item of getPendingAttachments()) {
    if (sentSet.has(item.id)) {
      if (item.previewUrl && !isBlobReferencedInSessionMessages(item.previewUrl, sessionId)) {
        // 保留在 blobUrlCache 供即将到达的本会话消息画廊直接复用，不泄露跨会话引用
        if (sessionId && item.id) {
          getBlobCache().set(`${sessionId}:${item.id}`, item.previewUrl);
        } else {
          safeRevokeObjectUrl(item.previewUrl);
        }
      }
    } else {
      kept.push(item);
    }
  }
  setPendingAttachments(kept);
  renderPendingAttachmentTray();
  emitUploadStateChanged();
}

export function resetAttachmentsForSessionSwitch(nextSessionId) {
  const prevSid = getCurrentSessionId();
  for (const item of getPendingAttachments()) {
    if (item?.previewUrl) {
      safeRevokeObjectUrl(item.previewUrl);
    }
    if (item?.id && (item.sessionId || prevSid)) {
      getBlobCache().delete(`${item.sessionId || prevSid}:${item.id}`);
    }
  }
  setPendingAttachments([]);

  const cache = getBlobCache();
  for (const [key, url] of Array.from(cache.entries())) {
    if (!nextSessionId || !key.startsWith(`${nextSessionId}:`)) {
      safeRevokeObjectUrl(url);
      cache.delete(key);
    }
  }
  getMsgAttachmentMap().clear();
  renderPendingAttachmentTray();
  emitUploadStateChanged();
}

export function handleRemoteAttachmentDeleted(attId, sessionId = "") {
  const sid = sessionId || getCurrentSessionId();
  const cur = getPendingAttachments();
  const target = cur.find((x) => x.id === attId);
  if (target) {
    revokePendingAttachmentUrl(target, sid);
    setPendingAttachments(cur.filter((x) => x.id !== attId));
    renderPendingAttachmentTray();
    emitUploadStateChanged();
  }
  if (sid && attId) {
    const cKey = `${sid}:${attId}`;
    const cachedUrl = getBlobCache().get(cKey);
    if (cachedUrl) {
      safeRevokeObjectUrl(cachedUrl);
      getBlobCache().delete(cKey);
    }
  }
}

/* ==================== 多模态二进制流直传、预览与删除闭环 ==================== */

async function fetchAttachmentBlobUrl(sessionId, attId, existingPreview = "") {
  if (existingPreview) return existingPreview;
  const cache = getBlobCache();
  const cacheKey = `${sessionId}:${attId}`;
  if (cache.has(cacheKey)) {
    return cache.get(cacheKey);
  }
  const token = getAuthToken();
  if (!token || !sessionId || !attId) return "";
  try {
    const res = await fetch(
      `/api/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(attId)}/raw`,
      {
        method: "GET",
        headers: { "X-Roundtable-Token": token },
      }
    );
    if (!res.ok) return "";
    if (getCurrentSessionId() !== sessionId) return "";
    const blob = await res.blob();
    if (getCurrentSessionId() !== sessionId) return "";
    const objUrl = URL.createObjectURL(blob);
    cache.set(cacheKey, objUrl);
    return objUrl;
  } catch {
    return "";
  }
}

export async function handleSelectedFiles(fileList) {
  const files = Array.from(fileList || []).filter(Boolean);
  if (!files.length) return;
  if (storeBridge.state?.snapshotLoading) {
    notifyToast("正在同步会话快照，请稍候添加附件", "warn");
    return;
  }
  const targetSessionId = getCurrentSessionId();
  if (!targetSessionId) {
    notifyToast("正在初始化本地会话，请稍候再试", "warn");
    return;
  }

  for (const file of files.slice(0, 10)) {
    if (file.size > 12 * 1024 * 1024) {
      notifyToast(`「${file.name}」超过 12 MB 单文件上限，已跳过`, "warn");
      continue;
    }
    const tempKey = `tmp_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const isImg = /^image\/(png|jpeg|webp|gif)$/i.test(file.type);
    const localPreviewUrl = isImg ? URL.createObjectURL(file) : "";
    const fallbackName = `粘贴截图_${new Date().toTimeString().slice(0, 8).replace(/:/g, "")}.png`;
    const fileName = file.name || fallbackName;
    const placeholder = {
      tempKey,
      id: "",
      sessionId: targetSessionId,
      name: fileName,
      kind: isImg ? "image" : "doc",
      mime_type: file.type || "application/octet-stream",
      size_human: file.size < 1024 ? `${file.size} B` : `${(file.size / 1024).toFixed(1)} KB`,
      width: 0,
      height: 0,
      line_count: 0,
      ext: (fileName.match(/\.[A-Za-z0-9]+$/) || [""])[0],
      previewUrl: localPreviewUrl,
      uploading: true,
    };
    getPendingAttachments().push(placeholder);
    renderPendingAttachmentTray();
    emitUploadStateChanged();

    try {
      const rawBuf = await file.arrayBuffer();
      const token = getAuthToken();
      const res = await fetch(`/api/sessions/${encodeURIComponent(targetSessionId)}/attachments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Attachment-Filename": encodeURIComponent(placeholder.name),
          "X-Attachment-Mime": placeholder.mime_type || "application/octet-stream",
          ...(token ? { "X-Roundtable-Token": token } : {}),
        },
        body: rawBuf,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data?.attachment?.id) {
        throw new Error(data.error || `上传失败 (${res.status})`);
      }
      const saved = data.attachment;
      // 跨会话归属二次核验：若上传期间用户已切走会话，立即回收本地预览 URL 并不污染新会话托盘
      if (getCurrentSessionId() !== targetSessionId) {
        safeRevokeObjectUrl(localPreviewUrl);
        continue;
      }
      if (localPreviewUrl) {
        getBlobCache().set(`${targetSessionId}:${saved.id}`, localPreviewUrl);
      }
      const list = getPendingAttachments();
      const idx = list.findIndex((x) => x.tempKey === tempKey);
      if (idx >= 0) {
        const dupIdx = list.findIndex((x, i) => i !== idx && x.id === saved.id);
        if (dupIdx >= 0) {
          safeRevokeObjectUrl(localPreviewUrl);
          list.splice(idx, 1);
        } else {
          list[idx] = {
            ...saved,
            sessionId: targetSessionId,
            previewUrl: localPreviewUrl,
            uploading: false,
          };
        }
      } else {
        safeRevokeObjectUrl(localPreviewUrl);
      }
      renderPendingAttachmentTray();
      emitUploadStateChanged();
      ensureSendableWithAttachmentOnly();
    } catch (err) {
      safeRevokeObjectUrl(localPreviewUrl);
      if (getCurrentSessionId() === targetSessionId) {
        setPendingAttachments(getPendingAttachments().filter((x) => x.tempKey !== tempKey));
        renderPendingAttachmentTray();
        emitUploadStateChanged();
      }
      notifyToast(err.message || `上传附件 ${fileName} 失败`, "err");
    }
  }
}

function ensureSendableWithAttachmentOnly() {
  const inp = $id("topicInput");
  if (!inp) return;
  if (getReadyPendingAttachments().length > 0 && !inp.placeholder.includes("可直接点击")) {
    inp.placeholder = "已就绪附件 · 可补充说明，或直接按 Enter / 点击右侧按钮开启多模态研讨";
  }
}

export function renderPendingAttachmentTray() {
  const tray = $id("v4AttachmentTray");
  if (!tray) return;
  const list = getPendingAttachments();
  if (!list.length) {
    tray.classList.add("hidden");
    tray.innerHTML = "";
    return;
  }
  tray.classList.remove("hidden");
  tray.innerHTML = list
    .map((att, idx) => {
      const extLabel =
        String(att.ext || "").replace(".", "").toUpperCase().slice(0, 4) ||
        (att.kind === "code" ? "CODE" : "FILE");
      const metaParts = [];
      if (att.uploading) {
        metaParts.push("上传校验中…");
      } else {
        if (att.width && att.height) metaParts.push(`${att.width}×${att.height}`);
        if (att.line_count > 0) metaParts.push(`${att.line_count} 行`);
        if (att.size_human) metaParts.push(att.size_human);
      }
      const visualHtml =
        att.kind === "image" && att.previewUrl
          ? `<img class="v4-att-thumb" src="${escapeAttr(att.previewUrl)}" alt="${escapeAttr(att.name)}" data-v4-zoom-idx="${idx}" />`
          : `<span class="v4-att-file-badge ${att.kind === "doc" ? "kind-doc" : ""}">${escapeAttr(extLabel)}</span>`;

      return (
        `<div class="v4-att-card${att.uploading ? " is-uploading" : ""}">` +
        visualHtml +
        `<div class="v4-att-info">` +
        `<span class="v4-att-name" title="${escapeAttr(att.name)}">${escapeAttr(att.name)}</span>` +
        `<span class="v4-att-meta">${escapeAttr(metaParts.join(" · "))}</span>` +
        `</div>` +
        `<button type="button" class="v4-att-remove" data-v4-rm-idx="${idx}" title="移除该附件" aria-label="移除该附件">${LINEAR_UI_ICONS.close}</button>` +
        `</div>`
      );
    })
    .join("");

  tray.querySelectorAll("[data-v4-zoom-idx]").forEach((imgEl) => {
    imgEl.onclick = (e) => {
      e.stopPropagation();
      const item = getPendingAttachments()[Number(imgEl.dataset.v4ZoomIdx)];
      if (item?.previewUrl) {
        openImageLightbox(
          item.previewUrl,
          `${item.name} (${item.width && item.height ? `${item.width}×${item.height} · ` : ""}${item.size_human || ""})`
        );
      }
    };
  });

  tray.querySelectorAll("[data-v4-rm-idx]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const targetSid = getCurrentSessionId();
      const listNow = getPendingAttachments();
      const idx = Number(btn.dataset.v4RmIdx);
      const removed = listNow[idx];
      if (!removed) return;
      listNow.splice(idx, 1);
      revokePendingAttachmentUrl(removed, targetSid);
      renderPendingAttachmentTray();
      emitUploadStateChanged();
      const token = getAuthToken();
      if (removed.id && targetSid && token) {
        fetch(
          `/api/sessions/${encodeURIComponent(targetSid)}/attachments/${encodeURIComponent(removed.id)}`,
          {
            method: "DELETE",
            headers: { "X-Roundtable-Token": token },
          }
        ).catch(() => {});
      }
    };
  });
}

export function openImageLightbox(src, caption = "") {
  const modal = $id("v4LightboxModal");
  const img = $id("v4LightboxImg");
  const cap = $id("v4LightboxCaption");
  if (!modal || !img) return;
  img.src = src;
  if (cap) cap.textContent = caption || "图片预览";
  modal.classList.remove("hidden");
}

export function closeImageLightbox() {
  const modal = $id("v4LightboxModal");
  if (modal) modal.classList.add("hidden");
}

export async function decorateMessageCardAttachments(cardEl, msgObj, fixedSessionId = "") {
  if (!cardEl || !msgObj?.id) return;
  const sid = fixedSessionId || getCurrentSessionId();
  const atts = Array.isArray(msgObj.attachments)
    ? msgObj.attachments
    : getMsgAttachmentMap().get(msgObj.id);
  if (!Array.isArray(atts) || !atts.length) return;

  getMsgAttachmentMap().set(msgObj.id, atts);
  let gallery = cardEl.querySelector(".v4-msg-attachments");
  if (gallery && Number(gallery.dataset.attCount || "0") === atts.length && gallery.childElementCount > 0) {
    return;
  }
  if (!gallery) {
    gallery = document.createElement("div");
    gallery.className = "v4-msg-attachments";
    cardEl.appendChild(gallery);
  }
  gallery.dataset.attCount = String(atts.length);

  const parts = [];
  for (const att of atts) {
    if (att.kind === "image") {
      const blobUrl = await fetchAttachmentBlobUrl(sid, att.id);
      if (getCurrentSessionId() !== sid) return;
      if (blobUrl) {
        const cap = `${att.name}${att.width && att.height ? ` · ${att.width}×${att.height}` : ""}`;
        parts.push(
          `<div class="v4-msg-img-card" data-lightbox-src="${escapeAttr(blobUrl)}" data-lightbox-cap="${escapeAttr(cap)}">` +
            `<img src="${escapeAttr(blobUrl)}" alt="${escapeAttr(att.name)}" />` +
            `<div class="v4-msg-img-cap">${escapeAttr(att.name)}</div>` +
            `</div>`
        );
        continue;
      }
    }
    const meta = att.line_count > 0 ? `${att.line_count} 行` : att.size_human || "";
    parts.push(
      `<span class="v4-msg-doc-pill">` +
        `${LINEAR_UI_ICONS.paperclip}<span>${escapeAttr(att.name)}</span>` +
        (meta ? `<em>${escapeAttr(meta)}</em>` : "") +
        `</span>`
    );
  }
  if (!cardEl.isConnected || getCurrentSessionId() !== sid) return;
  gallery.innerHTML = parts.join("");
  gallery.querySelectorAll("[data-lightbox-src]").forEach((node) => {
    node.onclick = (e) => {
      e.stopPropagation();
      openImageLightbox(node.dataset.lightboxSrc, node.dataset.lightboxCap);
    };
  });
}

/* ==================== 局部空心线性矢量徽标与白板微图标水合器（零全文档轮询） ==================== */

export function hydrateVectorIcons(scopeRoot = document) {
  const root = scopeRoot && typeof scopeRoot.querySelectorAll === "function" ? scopeRoot : document;

  root.querySelectorAll("[data-seat-icon]").forEach((node) => {
    const key = node.dataset.seatIcon;
    const svg = SEAT_VECTOR_ICONS[key];
    if (svg && !node.querySelector("svg")) {
      node.innerHTML = svg;
    }
  });

  const msgCards =
    root.classList && root.classList.contains("msg-card")
      ? [root]
      : Array.from(root.querySelectorAll(".msg-card"));
  for (const card of msgCards) {
    const av = card.querySelector(".msg-avatar-mini");
    if (av && !av.querySelector("svg")) {
      for (const key of Object.keys(SEAT_VECTOR_ICONS)) {
        if (card.classList.contains(`speaker-${key}`)) {
          av.innerHTML = SEAT_VECTOR_ICONS[key];
          break;
        }
      }
    }
    const copyBtn = card.querySelector("[data-msg-act='copy']");
    if (copyBtn && !copyBtn.querySelector("svg")) {
      copyBtn.innerHTML = `${LINEAR_UI_ICONS.copy}<span>复制</span>`;
    }
  }

  root.querySelectorAll(".wb-seat-mini-badge").forEach((badge) => {
    const dot = badge.querySelector(".mini-seat-dot");
    if (!dot || dot.querySelector("svg")) return;
    for (const key of Object.keys(SEAT_VECTOR_ICONS)) {
      if (badge.classList.contains(`badge-seat-${key}`)) {
        dot.innerHTML = SEAT_VECTOR_ICONS[key];
        break;
      }
    }
  });

  root.querySelectorAll(".wb-pool-actions").forEach((bar) => {
    const pinBtn = bar.querySelector("[data-wb-act='pin']");
    if (pinBtn && !pinBtn.querySelector("svg")) {
      const lbl = pinBtn.textContent.trim();
      pinBtn.innerHTML = `${LINEAR_UI_ICONS.pin}<span>${escapeAttr(lbl)}</span>`;
    }
    const adoptBtn = bar.querySelector("[data-wb-act='adopt']");
    if (adoptBtn && !adoptBtn.querySelector("svg")) {
      adoptBtn.innerHTML = `${LINEAR_UI_ICONS.adopt}<span>采纳为共识</span>`;
    }
    const discBtn = bar.querySelector("[data-wb-act='discuss']");
    if (discBtn && !discBtn.querySelector("svg")) {
      discBtn.innerHTML = `${LINEAR_UI_ICONS.discuss}<span>定向讨论</span>`;
    }
    const editBtn = bar.querySelector("[data-wb-act='edit']");
    if (editBtn && !editBtn.querySelector("svg")) {
      editBtn.innerHTML = `${LINEAR_UI_ICONS.edit}<span>编辑</span>`;
    }
    const delBtn = bar.querySelector("[data-wb-act='del']");
    if (delBtn && !delBtn.querySelector("svg")) {
      delBtn.innerHTML = LINEAR_UI_ICONS.close;
    }
  });

  root.querySelectorAll(".session-del-btn, .chip-file-remove").forEach((btn) => {
    if (!btn.querySelector("svg")) {
      btn.innerHTML = LINEAR_UI_ICONS.close;
    }
  });
  root.querySelectorAll(".wb-task-check.checked").forEach((chk) => {
    if (!chk.querySelector("svg")) {
      chk.innerHTML = `<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="5 12.5 9.6 17 19 7.5"></polyline></svg>`;
    }
  });
}

/* ==================== 单源 driver_catalog 动态模型快选芯片与档位胶囊 ==================== */

function formatModelShortLabel(modelId, specLabel = "") {
  if (specLabel) return specLabel;
  const clean = String(modelId || "").trim();
  if (!clean) return "跟随驱动默认";
  if (clean.startsWith("gemini-4-")) {
    const suffix = clean.slice("gemini-4-".length);
    return suffix.charAt(0).toUpperCase() + suffix.slice(1);
  }
  if (clean === "grok-4.7") return "Grok 4.7";
  if (clean === "gpt-6-astra") return "GPT-6 Astra";
  if (clean === "gpt-6.1-sol") return "GPT-6.1 Sol";
  return clean;
}

function buildDynamicModelChipsForDriver(driverKey) {
  const catalog = storeBridge.state?.system?.driver_catalog;
  const driversMap = catalog?.drivers || {};
  const drv = String(driverKey || "auto").toLowerCase();

  if (drv !== "auto" && driversMap[drv]) {
    const dEntry = driversMap[drv];
    if (Array.isArray(dEntry.recommended_models) && dEntry.recommended_models.length > 0) {
      return dEntry.recommended_models.map((item) =>
        typeof item === "string"
          ? { value: item, label: formatModelShortLabel(item) }
          : { value: String(item.value || item.id || ""), label: formatModelShortLabel(item.value || item.id, item.label) }
      );
    }
    const modelsObj = dEntry.models || {};
    const concreteKeys = Object.keys(modelsObj).filter(
      (k) =>
        k &&
        !k.includes("*") &&
        !k.includes("(") &&
        !k.startsWith("gemini-pro-orchestrator") &&
        modelsObj[k]?.supports_effort !== false
    );
    if (concreteKeys.length > 0) {
      return concreteKeys.map((k) => ({
        value: k,
        label: formatModelShortLabel(k, modelsObj[k]?.label || ""),
      }));
    }
  }

  // auto 驱动：聚合各已声明驱动的默认代表模型
  const autoChips = [{ value: "", label: "跟随驱动默认" }];
  const seen = new Set([""]);
  for (const dk of Object.keys(driversMap)) {
    const defModel = String(driversMap[dk]?.default_model || "").trim();
    if (defModel && !seen.has(defModel)) {
      seen.add(defModel);
      autoChips.push({ value: defModel, label: formatModelShortLabel(defModel) });
    }
  }
  return autoChips;
}

export function renderSeatModelAndEffortChips(seatCap) {
  const drvSel = $id(`cfg${seatCap}Driver`);
  const modelInp = $id(`cfg${seatCap}Model`);
  const chipBar = $id(`v4ModelChips${seatCap}`);
  const discSel = $id(`cfg${seatCap}Effort`);
  const execSel = $id(`cfg${seatCap}ExecEffort`);
  const effortSeg = $id(`v4EffortSeg${seatCap}`);
  if (!drvSel || !modelInp || !chipBar || !discSel || !effortSeg) return;

  const drv = drvSel.value || "auto";
  const chips = buildDynamicModelChipsForDriver(drv);
  const curModel = modelInp.value.trim();
  const matchesPreset = chips.some((c) => c.value.toLowerCase() === curModel.toLowerCase());

  chipBar.innerHTML = chips
    .map((c) => {
      const isAct =
        c.value.toLowerCase() === curModel.toLowerCase() || (!curModel && chips[0] && c.value === chips[0].value);
      return `<button type="button" class="v4-model-chip${isAct ? " active" : ""}" data-chip-model="${escapeAttr(c.value)}">${escapeAttr(c.label)}</button>`;
    })
    .join("");

  if (curModel && !matchesPreset) {
    modelInp.classList.remove("hidden");
  }

  chipBar.querySelectorAll("[data-chip-model]").forEach((btn) => {
    btn.onclick = () => {
      modelInp.value = btn.dataset.chipModel || "";
      modelInp.dispatchEvent(new Event("input", { bubbles: true }));
      modelInp.dispatchEvent(new Event("change", { bubbles: true }));
      setTimeout(() => renderSeatModelAndEffortChips(seatCap), 20);
    };
  });

  if (discSel.disabled || !discSel.options.length || (discSel.options.length === 1 && !discSel.options[0].value)) {
    effortSeg.innerHTML = `<span class="v4-effort-muted-tag">自动省略档位</span>`;
  } else {
    const opts = Array.from(discSel.options).filter((o) => o.value);
    if (!opts.length) {
      effortSeg.innerHTML = `<span class="v4-effort-muted-tag">自动省略档位</span>`;
      return;
    }
    const activeVal = discSel.value || opts[opts.length - 1]?.value || "high";
    effortSeg.innerHTML = opts
      .map(
        (o) =>
          `<button type="button" class="v4-effort-pill-btn${o.value === activeVal ? " active" : ""}" data-eff-val="${escapeAttr(
            o.value
          )}">${escapeAttr(o.value)}</button>`
      )
      .join("");

    effortSeg.querySelectorAll("[data-eff-val]").forEach((ebtn) => {
      ebtn.onclick = () => {
        const v = ebtn.dataset.effVal || "high";
        discSel.value = v;
        discSel.dispatchEvent(new Event("change", { bubbles: true }));
        if (execSel && !execSel.disabled) {
          const allowedExec = Array.from(execSel.options).map((o) => o.value);
          if (allowedExec.includes(v)) {
            execSel.value = v;
          }
        }
        renderSeatModelAndEffortChips(seatCap);
      };
    });
  }
}

export function refreshAllModalSeatChips() {
  SEAT_CAPS.forEach((cap) => renderSeatModelAndEffortChips(cap));
}

export function syncComposerStrategySummary() {
  const txtEl = $id("v4StrategySummaryText");
  const autoDot = $id("v4AutoExecDot");
  if (!txtEl) return;

  const activeModeBtn = document.querySelector("#inlineModeSelect .mode-seg-pill.active");
  const modeKey = activeModeBtn?.dataset.collabOpt || storeBridge.state?.collabMode || "deep_deliberation";
  const modeLabel = MODE_SHORT_LABELS[modeKey] || "深度研讨";

  const ringCountTxt = ($id("ringSeatCountLabel")?.textContent || "3 席").replace("参会", "").trim();
  const summary = `${modeLabel} · ${ringCountTxt}`;
  if (txtEl.textContent !== summary) txtEl.textContent = summary;

  const autoOn = Boolean($id("composerAutoPreviewBtn")?.classList.contains("active"));
  autoDot?.classList.toggle("hidden", !autoOn);
}

export function closeV4Popovers() {
  $id("v4AttachPopover")?.classList.add("hidden");
  $id("v4PlusAttachBtn")?.setAttribute("aria-expanded", "false");
  $id("v4ModePopover")?.classList.add("hidden");
  $id("v4ModeTriggerPill")?.setAttribute("aria-expanded", "false");
}

export function initV4Enhancements() {
  if (storeBridge.initialized) return;
  storeBridge.initialized = true;

  hydrateVectorIcons(document);
  syncComposerStrategySummary();

  const morePresetsBtn = $id("v4ToggleMorePresetsBtn");
  morePresetsBtn?.addEventListener("click", () => {
    const extras = document.querySelectorAll(".v4-extra-scenario");
    const isNowOpen = extras[0]?.classList.contains("hidden");
    extras.forEach((card) => card.classList.toggle("hidden", !isNowOpen));
    morePresetsBtn.setAttribute("aria-expanded", isNowOpen ? "true" : "false");
    const span = morePresetsBtn.querySelector("span");
    if (span) span.textContent = isNowOpen ? "收起 4–6 席高阶阵容" : "展开 4–6 席高阶阵容";
  });

  document.querySelectorAll("[data-prompt-slot]").forEach((pill) => {
    pill.addEventListener("click", () => {
      const inp = $id("topicInput");
      if (!inp) return;
      const snippet = pill.dataset.promptSlot || "";
      if (!snippet) return;
      const cur = inp.value || "";
      if (!cur.includes(snippet.trim())) {
        inp.value = cur ? `${cur.replace(/\s+$/, "")}${snippet}` : snippet.trimStart();
        inp.dispatchEvent(new Event("input", { bubbles: true }));
      }
      inp.focus();
      inp.setSelectionRange(inp.value.length, inp.value.length);
    });
  });

  const fileInp = $id("v4HiddenFileInput");
  const imgInp = $id("v4HiddenImageInput");

  $id("v4PlusAttachBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    const pop = $id("v4AttachPopover");
    const shouldOpen = pop?.classList.contains("hidden");
    closeV4Popovers();
    if (shouldOpen && pop) {
      pop.classList.remove("hidden");
      $id("v4PlusAttachBtn")?.setAttribute("aria-expanded", "true");
    }
  });

  document.querySelectorAll("[data-v4-attach-cmd]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const cmd = btn.dataset.v4AttachCmd;
      closeV4Popovers();
      if (cmd === "image") imgInp?.click();
      else if (cmd === "file") fileInp?.click();
      else if (cmd === "at-code") $id("insertFileRefBtn")?.click();
    });
  });

  $id("v4QuickImageBtn")?.addEventListener("click", () => imgInp?.click());
  $id("v4QuickDocBtn")?.addEventListener("click", () => fileInp?.click());
  $id("railAttachQuickBtn")?.addEventListener("click", () => fileInp?.click());

  fileInp?.addEventListener("change", async () => {
    if (fileInp.files?.length) {
      await handleSelectedFiles(fileInp.files);
      fileInp.value = "";
    }
  });
  imgInp?.addEventListener("change", async () => {
    if (imgInp.files?.length) {
      await handleSelectedFiles(imgInp.files);
      imgInp.value = "";
    }
  });

  document.addEventListener("paste", async (e) => {
    const activeTag = document.activeElement?.tagName || "";
    const inModalInput = document.activeElement?.closest("#settingsModal") && activeTag === "INPUT";
    if (inModalInput) return;

    const items = Array.from(e.clipboardData?.items || []);
    const fileObjs = [];
    for (const it of items) {
      if (it.kind === "file") {
        const f = it.getAsFile();
        if (f) fileObjs.push(f);
      }
    }
    if (fileObjs.length > 0) {
      e.preventDefault();
      await handleSelectedFiles(fileObjs);
      $id("topicInput")?.focus();
    }
  });

  const dropOverlay = $id("v4DropOverlay");
  window.addEventListener("dragenter", (e) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    storeBridge.dragDepth += 1;
    dropOverlay?.classList.remove("hidden");
  });
  window.addEventListener("dragover", (e) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  });
  window.addEventListener("dragleave", (e) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    storeBridge.dragDepth = Math.max(0, storeBridge.dragDepth - 1);
    if (storeBridge.dragDepth === 0) {
      dropOverlay?.classList.add("hidden");
    }
  });
  window.addEventListener("drop", async (e) => {
    if (!e.dataTransfer?.files?.length) return;
    e.preventDefault();
    storeBridge.dragDepth = 0;
    dropOverlay?.classList.add("hidden");
    await handleSelectedFiles(e.dataTransfer.files);
    $id("topicInput")?.focus();
  });

  $id("v4ModeTriggerPill")?.addEventListener("click", (e) => {
    e.stopPropagation();
    const pop = $id("v4ModePopover");
    const shouldOpen = pop?.classList.contains("hidden");
    closeV4Popovers();
    if (shouldOpen && pop) {
      pop.classList.remove("hidden");
      $id("v4ModeTriggerPill")?.setAttribute("aria-expanded", "true");
    }
  });
  $id("v4ModePopover")?.addEventListener("click", (e) => e.stopPropagation());
  $id("v4OpenFullSettingsLink")?.addEventListener("click", () => {
    closeV4Popovers();
    $id("railSettingsBtn")?.click();
  });

  $id("settingsModal")?.addEventListener("roundtable:settings-open", refreshAllModalSeatChips);

  SEAT_CAPS.forEach((cap) => {
    $id(`cfg${cap}Driver`)?.addEventListener("change", () => setTimeout(() => renderSeatModelAndEffortChips(cap), 25));
    $id(`cfg${cap}Model`)?.addEventListener("input", () => renderSeatModelAndEffortChips(cap));
    $id(`cfg${cap}Model`)?.addEventListener("change", () => renderSeatModelAndEffortChips(cap));
    $id(`cfg${cap}Effort`)?.addEventListener("change", () => renderSeatModelAndEffortChips(cap));
    document.querySelector(`[data-v4-toggle-custom="${cap}"]`)?.addEventListener("click", () => {
      const inp = $id(`cfg${cap}Model`);
      if (!inp) return;
      const nowHidden = inp.classList.toggle("hidden");
      if (!nowHidden) inp.focus();
    });
  });

  $id("v4LightboxCloseBtn")?.addEventListener("click", closeImageLightbox);
  $id("v4LightboxModal")?.addEventListener("click", (e) => {
    if (e.target === $id("v4LightboxModal")) closeImageLightbox();
  });

  document.addEventListener("click", () => closeV4Popovers());
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "u") {
      e.preventDefault();
      fileInp?.click();
    } else if (e.key === "Escape") {
      closeImageLightbox();
      closeV4Popovers();
    }
  });

  const prevMenuHook = window.__roundtableMenu;
  window.__roundtableMenu = function patchedRoundtableMenu(cmd) {
    if (cmd === "attachFiles") {
      fileInp?.click();
      return;
    }
    if (typeof prevMenuHook === "function") {
      prevMenuHook(cmd);
    }
  };
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initV4Enhancements);
} else {
  initV4Enhancements();
}
