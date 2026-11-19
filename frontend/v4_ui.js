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
  layers: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 3.2 20.4 7.6 12 12 3.6 7.6 12 3.2"></polygon><polyline points="3.6 12.2 12 16.6 20.4 12.2"></polyline><polyline points="6.2 16.5 12 19.6 17.8 16.5"></polyline></svg>`,
  chevronDown: `<svg class="v4-inline-svg v4-caret-svg" viewBox="0 0 24 24" width="12.5" height="12.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"></polyline></svg>`,
  chevronRight: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="11.5" height="11.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 6 15 12 9 18"></polyline></svg>`,
  search: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12.5" height="12.5" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><line x1="16.4" y1="16.4" x2="20.6" y2="20.6"></line></svg>`,
  check: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="5 12.5 9.6 17 19 7.5"></polyline></svg>`,
  lockCap: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="10.5" height="10.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"></rect><path d="M8 11V7.5a4 4 0 0 1 8 0V11"></path></svg>`,
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

/* ==================== 订阅档位兼容计算、玻璃自定义下拉框与两栏分级级联模型选择器 ==================== */

const EFFORT_RANK_ORDER = ["minimal", "low", "medium", "high", "xhigh", "max"];
const SUB_TIER_RANKS = { all: 99, free: 0, plus_pro: 1, max_ultra: 2, api_local: 3 };
const SUB_TIER_KEYS_BY_RANK = { 0: "free", 1: "plus_pro", 2: "max_ultra", 3: "api_local", 99: "all" };
const TIER_MIN_SHORT_BADGE = { 0: "Free", 1: "Plus·Pro", 2: "Max·Ultra", 3: "API" };

const cascadeUiState = new Map();

function getCatalogRoot() {
  return storeBridge.state?.system?.driver_catalog || storeBridge.state?.system?.model_effort_catalog || {};
}

export function resolveDriverSubscriptionProfile(driverKey) {
  const cat = getCatalogRoot();
  const st = storeBridge.state || {};
  const globalTier = String(st.subscriptionTier || st.system?.subscription_tier || "all").toLowerCase();
  const vendorMap = st.vendorSubscriptions || st.system?.vendor_subscriptions || {};
  const drv = String(driverKey || "agy").toLowerCase();

  const vPlanKey = vendorMap[drv];
  const vPlans = cat.vendor_plans?.[drv]?.plans;
  if (vPlanKey && vPlanKey !== "auto" && Array.isArray(vPlans)) {
    const found = vPlans.find((p) => p.key === vPlanKey);
    if (found && typeof found.rank === "number" && found.rank >= 0) {
      return {
        tierKey: SUB_TIER_KEYS_BY_RANK[found.rank] || "plus_pro",
        rank: found.rank,
        planLabel: found.label,
        effortCap: found.effort_cap || "",
        isFiltered: true,
      };
    }
  }
  const rank = SUB_TIER_RANKS[globalTier] ?? 99;
  const tierSpec = cat.subscription_tiers?.[globalTier];
  return {
    tierKey: globalTier,
    rank,
    planLabel: tierSpec?.label || "全部可用模型",
    effortCap: globalTier === "free" ? "high" : "",
    isFiltered: rank < 99,
  };
}

export function evaluateModelSubscriptionFit(driverKey, modelId, modelSpec = null) {
  const cat = getCatalogRoot();
  const drv = String(driverKey || "agy").toLowerCase();
  const cleanId = String(modelId || "").trim().toLowerCase();
  const spec = modelSpec || cat.drivers?.[drv]?.models?.[cleanId] || {};
  const prof = resolveDriverSubscriptionProfile(drv);
  const tierMin = typeof spec.tier_min === "number" ? spec.tier_min : 0;
  const unlocked = !prof.isFiltered || prof.rank >= tierMin;
  const modelTierCap = spec.effort_caps_by_tier?.[prof.tierKey] || "";
  const effortCap = prof.isFiltered ? modelTierCap || prof.effortCap || "" : "";
  return {
    unlocked,
    isFiltered: prof.isFiltered,
    tierMin,
    requiredBadge: TIER_MIN_SHORT_BADGE[tierMin] || "Pro",
    planBadge: spec.plan_badge || TIER_MIN_SHORT_BADGE[tierMin] || "",
    effortCap,
  };
}

export function isEffortAboveSubscriptionCap(effortVal, effortCap) {
  if (!effortVal || !effortCap) return false;
  const idxVal = EFFORT_RANK_ORDER.indexOf(String(effortVal).toLowerCase());
  const idxCap = EFFORT_RANK_ORDER.indexOf(String(effortCap).toLowerCase());
  if (idxVal < 0 || idxCap < 0) return false;
  return idxVal > idxCap;
}

function formatModelShortLabel(modelId, specLabel = "") {
  const clean = String(modelId || "").trim();
  if (!clean) return "跟随驱动默认";
  if (clean.startsWith("gemini-4-")) {
    const suffix = clean.slice("gemini-4-".length);
    return suffix.charAt(0).toUpperCase() + suffix.slice(1);
  }
  if (specLabel) return specLabel;
  if (clean === "grok-4.7") return "Grok 4.7";
  if (clean === "gpt-6-astra") return "GPT-6 Astra";
  if (clean === "gpt-6.1-sol") return "GPT-6.1 Sol";
  return clean;
}

function lookupModelDisplayMeta(driverKey, modelId) {
  const cat = getCatalogRoot();
  const driversMap = cat.drivers || {};
  const clean = String(modelId || "").trim();
  if (!clean) {
    return {
      id: "",
      label: "跟随驱动默认",
      shortLabel: "跟随驱动默认",
      groupLabel: "自动匹配",
      subgroupLabel: "默认主力",
      context: "",
      planBadge: "Auto",
      unlocked: true,
      driverKey: driverKey || "auto",
    };
  }
  const low = clean.toLowerCase();
  const searchDrivers = driverKey && driverKey !== "auto" && driversMap[driverKey]
    ? [driverKey]
    : Object.keys(driversMap);
  for (const dk of searchDrivers) {
    const dEntry = driversMap[dk] || {};
    const mSpec = dEntry.models?.[low] || dEntry.models?.[clean];
    if (mSpec) {
      const groups = Array.isArray(dEntry.model_groups) ? dEntry.model_groups : [];
      const gFound = groups.find((g) => g.key === mSpec.group);
      const fit = evaluateModelSubscriptionFit(dk, low, mSpec);
      return {
        id: clean,
        label: mSpec.label || formatModelShortLabel(clean),
        shortLabel: formatModelShortLabel(clean, mSpec.label || ""),
        groupLabel: gFound?.label || dEntry.short_label || dk.toUpperCase(),
        subgroupLabel: mSpec.subgroup || "",
        context: mSpec.context || "",
        planBadge: fit.planBadge,
        unlocked: fit.unlocked,
        requiredBadge: fit.requiredBadge,
        effortCap: fit.effortCap,
        supportsEffort: mSpec.supports_effort !== false,
        allowed: Array.isArray(mSpec.allowed) ? mSpec.allowed : [],
        note: mSpec.note || "",
        driverKey: dk,
      };
    }
  }
  return {
    id: clean,
    label: formatModelShortLabel(clean),
    shortLabel: formatModelShortLabel(clean),
    groupLabel: "自定义模型",
    subgroupLabel: "",
    context: "",
    planBadge: "Custom",
    unlocked: true,
    driverKey: driverKey || "auto",
  };
}

function buildCascadeHierarchy(driverKey) {
  const cat = getCatalogRoot();
  const driversMap = cat.drivers || {};
  const drv = String(driverKey || "auto").toLowerCase();

  if (drv !== "auto" && driversMap[drv]) {
    const dEntry = driversMap[drv];
    const modelsObj = dEntry.models || {};
    const rawGroups = Array.isArray(dEntry.model_groups) ? dEntry.model_groups : [];
    if (rawGroups.length > 0) {
      return rawGroups.map((grp) => {
        let totalCount = 0;
        let unlockedCount = 0;
        const subgroups = (grp.subgroups || []).map((sg) => {
          const items = (sg.models || [])
            .filter((mid) => modelsObj[mid.toLowerCase()] || modelsObj[mid])
            .map((mid) => {
              const meta = lookupModelDisplayMeta(drv, mid);
              totalCount += 1;
              if (meta.unlocked) unlockedCount += 1;
              return meta;
            });
          return { label: sg.label || "主力模型", items };
        }).filter((sg) => sg.items.length > 0);
        return {
          key: grp.key,
          label: grp.label,
          badge: grp.badge || "",
          desc: grp.desc || "",
          totalCount,
          unlockedCount,
          subgroups,
        };
      }).filter((g) => g.subgroups.length > 0);
    }
    const concrete = Object.keys(modelsObj).filter((k) => k && !k.includes("*"));
    const items = concrete.map((mid) => lookupModelDisplayMeta(drv, mid));
    return [
      {
        key: `${drv}-all`,
        label: dEntry.cli_name || drv.toUpperCase(),
        badge: `${items.length}`,
        desc: "",
        totalCount: items.length,
        unlockedCount: items.filter((i) => i.unlocked).length,
        subgroups: [{ label: "可用模型", items }],
      },
    ];
  }

  // auto 驱动：按厂商 CLI 聚合全部模型大类
  const autoGroups = [
    {
      key: "auto-default",
      label: "自动跟随默认",
      badge: "Auto",
      desc: "根据本机就绪 CLI 自动选用对应主力模型",
      totalCount: 1,
      unlockedCount: 1,
      subgroups: [
        {
          label: "智能托管",
          items: [lookupModelDisplayMeta("auto", "")],
        },
      ],
    },
  ];
  for (const dk of Object.keys(driversMap)) {
    const dEntry = driversMap[dk];
    const modelsObj = dEntry.models || {};
    const subList = [];
    let totalCount = 0;
    let unlockedCount = 0;
    for (const grp of dEntry.model_groups || []) {
      const flatIds = (grp.subgroups || []).flatMap((sg) => sg.models || []);
      const items = flatIds
        .filter((mid) => modelsObj[mid.toLowerCase()] || modelsObj[mid])
        .map((mid) => {
          const meta = lookupModelDisplayMeta(dk, mid);
          totalCount += 1;
          if (meta.unlocked) unlockedCount += 1;
          return meta;
        });
      if (items.length > 0) {
        subList.push({ label: grp.label, items });
      }
    }
    if (subList.length > 0) {
      autoGroups.push({
        key: `drv-${dk}`,
        label: `${dEntry.provider || dk.toUpperCase()} · ${dEntry.short_label || dk}`,
        badge: dEntry.short_label || dk.toUpperCase(),
        desc: dEntry.cli_name || "",
        totalCount,
        unlockedCount,
        subgroups: subList,
      });
    }
  }
  return autoGroups;
}

const floatingMenuByWrap = new WeakMap();
let activeFloatingEntry = null;

function getFloatingPortalHost() {
  return $id("v4FloatingPortalHost") || document.body;
}

function positionFloatingLayer(triggerEl, floatingEl, kind = "select") {
  if (!triggerEl || !floatingEl || !triggerEl.isConnected) return;
  const rect = triggerEl.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) {
    closeCascadePickers();
    return;
  }
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const margin = 14;
  const gap = 6;

  floatingEl.style.position = "fixed";
  floatingEl.style.top = "auto";
  floatingEl.style.bottom = "auto";
  floatingEl.style.right = "auto";

  if (kind === "cascade") {
    const targetW = Math.min(568, vw - margin * 2);
    floatingEl.style.width = `${targetW}px`;
    const left = Math.min(Math.max(margin, rect.left), Math.max(margin, vw - targetW - margin));
    floatingEl.style.left = `${Math.round(left)}px`;

    const spaceBelow = vh - rect.bottom - margin - gap;
    const spaceAbove = rect.top - margin - gap;
    const flipUp = spaceBelow < 270 && spaceAbove > spaceBelow;
    const availH = Math.max(190, flipUp ? spaceAbove : spaceBelow);
    const colsEl = floatingEl.querySelector(".v4-cascade-columns");
    if (colsEl) {
      const colsMax = Math.max(150, Math.min(340, availH - 58));
      colsEl.style.maxHeight = `${Math.round(colsMax)}px`;
    }
    if (flipUp) {
      floatingEl.style.bottom = `${Math.round(vh - rect.top + gap)}px`;
      floatingEl.style.transformOrigin = "bottom left";
    } else {
      floatingEl.style.top = `${Math.round(rect.bottom + gap)}px`;
      floatingEl.style.transformOrigin = "top left";
    }
  } else {
    const minW = Math.max(Math.round(rect.width), 268);
    const maxW = Math.min(480, vw - margin * 2);
    floatingEl.style.minWidth = `${Math.min(minW, maxW)}px`;
    floatingEl.style.maxWidth = `${maxW}px`;

    const spaceBelow = vh - rect.bottom - margin - gap;
    const spaceAbove = rect.top - margin - gap;
    const flipUp = spaceBelow < 220 && spaceAbove > spaceBelow;
    const maxH = Math.max(150, Math.min(320, flipUp ? spaceAbove : spaceBelow));
    floatingEl.style.maxHeight = `${Math.round(maxH)}px`;

    const measuredW = Math.min(maxW, Math.max(floatingEl.offsetWidth || minW, minW));
    const left = Math.min(Math.max(margin, rect.left), Math.max(margin, vw - measuredW - margin));
    floatingEl.style.left = `${Math.round(left)}px`;

    if (flipUp) {
      floatingEl.style.bottom = `${Math.round(vh - rect.top + gap)}px`;
      floatingEl.style.transformOrigin = "bottom left";
    } else {
      floatingEl.style.top = `${Math.round(rect.bottom + gap)}px`;
      floatingEl.style.transformOrigin = "top left";
    }
  }
}

function repositionActiveFloatingLayer() {
  if (!activeFloatingEntry) return;
  const { wrap, trigger, menu, kind } = activeFloatingEntry;
  if (!wrap?.isConnected || !trigger?.isConnected || menu.classList.contains("hidden")) {
    closeCascadePickers();
    return;
  }
  positionFloatingLayer(trigger, menu, kind);
}

export function closeCascadePickers(exceptContainer = null) {
  document.querySelectorAll(".v4-cascade-picker.is-open").forEach((wrap) => {
    if (exceptContainer && wrap === exceptContainer) return;
    wrap.classList.remove("is-open");
    floatingMenuByWrap.get(wrap)?.classList.add("hidden");
    wrap.querySelector(".v4-cascade-trigger")?.setAttribute("aria-expanded", "false");
  });
  document.querySelectorAll(".v4-glass-select-wrap.is-open").forEach((wrap) => {
    if (exceptContainer && wrap === exceptContainer) return;
    wrap.classList.remove("is-open");
    floatingMenuByWrap.get(wrap)?.classList.add("hidden");
    wrap.querySelector(".v4-glass-select-trigger")?.setAttribute("aria-expanded", "false");
  });
  if (!exceptContainer) {
    activeFloatingEntry = null;
  }
}

export function renderCascadingModelWidget(containerEl, { driverKey, currentModel, onSelectModel, compact = false }) {
  if (!containerEl) return;
  const groups = buildCascadeHierarchy(driverKey);
  const curMeta = lookupModelDisplayMeta(driverKey, currentModel || (driverKey !== "auto" ? getCatalogRoot()?.drivers?.[driverKey]?.default_model || "" : ""));
  const stateKey = containerEl.id || (compact ? "popover-cascade" : "seat-cascade");
  const prevUi = cascadeUiState.get(stateKey) || { activeGroupKey: "", searchQuery: "" };

  let activeGroupKey = prevUi.activeGroupKey;
  if (!groups.some((g) => g.key === activeGroupKey)) {
    const ownerGrp = groups.find((g) =>
      g.subgroups.some((sg) => sg.items.some((it) => it.id.toLowerCase() === String(curMeta.id || "").toLowerCase()))
    );
    activeGroupKey = ownerGrp?.key || groups[0]?.key || "";
    prevUi.activeGroupKey = activeGroupKey;
    cascadeUiState.set(stateKey, prevUi);
  }

  const prevPop = floatingMenuByWrap.get(containerEl);
  if (prevPop && prevPop.parentNode) {
    prevPop.remove();
  }
  containerEl.classList.remove("is-open");

  const fitTagHtml = curMeta.unlocked
    ? (curMeta.planBadge ? `<span class="v4-cascade-badge is-fit">${escapeAttr(curMeta.planBadge)}</span>` : "")
    : `<span class="v4-cascade-badge is-locked" title="当前所选订阅档位未包含该模型，需 ${escapeAttr(curMeta.requiredBadge || "高阶订阅")} 或 API">${LINEAR_UI_ICONS.lockCap}<span>需 ${escapeAttr(curMeta.requiredBadge || "Pro")}</span></span>`;

  containerEl.innerHTML =
    `<button type="button" class="v4-cascade-trigger${compact ? " is-compact" : ""}${!curMeta.unlocked ? " is-above-sub" : ""}" aria-haspopup="listbox" aria-expanded="false">` +
      `<span class="v4-cascade-trig-left">` +
        `${LINEAR_UI_ICONS.layers}` +
        `<span class="v4-cascade-crumb">${escapeAttr(curMeta.groupLabel)}</span>` +
        `<span class="v4-cascade-sep">/</span>` +
        `<strong class="v4-cascade-model-name">${escapeAttr(curMeta.label)}</strong>` +
      `</span>` +
      `<span class="v4-cascade-trig-right">` +
        (curMeta.context ? `<em class="v4-cascade-ctx">${escapeAttr(curMeta.context)}</em>` : "") +
        fitTagHtml +
        `${LINEAR_UI_ICONS.chevronDown}` +
      `</span>` +
    `</button>`;

  const popEl = document.createElement("div");
  popEl.className = "v4-cascade-popover hidden";
  popEl.setAttribute("role", "dialog");
  popEl.setAttribute("aria-label", "模型大类与子系列分级选择");
  popEl.innerHTML =
    `<div class="v4-cascade-search-row">` +
      `${LINEAR_UI_ICONS.search}` +
      `<input type="text" class="v4-cascade-search-inp" value="${escapeAttr(prevUi.searchQuery || "")}" placeholder="搜索模型大类、名称或上下文（如 gpt-6.2 / opus / 1M / free）…" />` +
    `</div>` +
    `<div class="v4-cascade-columns">` +
      `<div class="v4-cascade-groups" role="tablist"></div>` +
      `<div class="v4-cascade-items" role="listbox"></div>` +
    `</div>`;
  getFloatingPortalHost().appendChild(popEl);
  floatingMenuByWrap.set(containerEl, popEl);

  const trigBtn = containerEl.querySelector(".v4-cascade-trigger");
  const searchInp = popEl.querySelector(".v4-cascade-search-inp");
  const groupsCol = popEl.querySelector(".v4-cascade-groups");
  const itemsCol = popEl.querySelector(".v4-cascade-items");

  const renderColumns = () => {
    const q = String(searchInp?.value || "").trim().toLowerCase();
    prevUi.searchQuery = q;
    cascadeUiState.set(stateKey, prevUi);

    if (q) {
      groupsCol.classList.add("is-searching");
      groupsCol.innerHTML = `<div class="v4-cascade-search-hint">检索结果</div>`;
      const matchedSubgroups = [];
      for (const g of groups) {
        for (const sg of g.subgroups) {
          const hits = sg.items.filter((it) =>
            `${it.label} ${it.id} ${g.label} ${sg.label} ${it.planBadge} ${it.context} ${it.note}`.toLowerCase().includes(q)
          );
          if (hits.length > 0) {
            matchedSubgroups.push({ label: `${g.label} · ${sg.label}`, items: hits });
          }
        }
      }
      renderRightSubgroups(matchedSubgroups);
      return;
    }

    groupsCol.classList.remove("is-searching");
    const prof = resolveDriverSubscriptionProfile(driverKey === "auto" ? "agy" : driverKey);
    groupsCol.innerHTML = groups
      .map((g) => {
        const isAct = g.key === prevUi.activeGroupKey;
        const countTxt = prof.isFiltered ? `${g.unlockedCount}/${g.totalCount}` : `${g.totalCount}`;
        return (
          `<button type="button" class="v4-cascade-group-btn${isAct ? " active" : ""}" data-cascade-grp="${escapeAttr(g.key)}">` +
            `<div class="v4-cg-top"><span>${escapeAttr(g.label)}</span>${LINEAR_UI_ICONS.chevronRight}</div>` +
            `<div class="v4-cg-meta">` +
              (g.badge ? `<span class="v4-cg-badge">${escapeAttr(g.badge)}</span>` : "") +
              `<span class="v4-cg-count">${escapeAttr(countTxt)} 款</span>` +
            `</div>` +
          `</button>`
        );
      })
      .join("");

    groupsCol.querySelectorAll("[data-cascade-grp]").forEach((gBtn) => {
      const activateGrp = (ev) => {
        ev.stopPropagation();
        prevUi.activeGroupKey = gBtn.dataset.cascadeGrp;
        cascadeUiState.set(stateKey, prevUi);
        groupsCol.querySelectorAll("[data-cascade-grp]").forEach((b) => b.classList.toggle("active", b === gBtn));
        const chosenGrp = groups.find((x) => x.key === prevUi.activeGroupKey) || groups[0];
        renderRightSubgroups(chosenGrp ? chosenGrp.subgroups : []);
      };
      gBtn.addEventListener("click", activateGrp);
      gBtn.addEventListener("mouseenter", activateGrp);
    });

    const activeGrp = groups.find((x) => x.key === prevUi.activeGroupKey) || groups[0];
    renderRightSubgroups(activeGrp ? activeGrp.subgroups : []);
  };

  const renderRightSubgroups = (subgroups) => {
    if (!subgroups || subgroups.length === 0) {
      itemsCol.innerHTML = `<div class="v4-cascade-empty">未匹配到符合条件的模型，可直接点击右上角「自定义模型 ID」手动输入</div>`;
      return;
    }
    const curIdLow = String(curMeta.id || "").toLowerCase();
    itemsCol.innerHTML = subgroups
      .map((sg) => {
        const rowsHtml = sg.items
          .map((it) => {
            const isSel = it.id.toLowerCase() === curIdLow;
            const effRange =
              it.supportsEffort === false
                ? "免填档位"
                : it.allowed?.length
                ? `${it.allowed[0]}–${it.allowed[it.allowed.length - 1]}`
                : "low–high";
            const subPill = it.unlocked
              ? `<span class="v4-cm-sub is-ok">${escapeAttr(it.planBadge || "可用")}</span>`
              : `<span class="v4-cm-sub is-warn">${LINEAR_UI_ICONS.lockCap}<span>需 ${escapeAttr(it.requiredBadge || "高阶")}</span></span>`;
            return (
              `<button type="button" class="v4-cascade-item-btn${isSel ? " selected" : ""}${!it.unlocked ? " is-above-tier" : ""}" data-cascade-model="${escapeAttr(it.id)}" data-cascade-drv="${escapeAttr(it.driverKey || "")}">` +
                `<div class="v4-cm-main">` +
                  `<span class="v4-cm-title">${escapeAttr(it.label)}</span>` +
                  (it.id ? `<code class="v4-cm-code">${escapeAttr(it.id)}</code>` : "") +
                  (isSel ? `<span class="v4-cm-check">${LINEAR_UI_ICONS.check}</span>` : "") +
                `</div>` +
                `<div class="v4-cm-tags">` +
                  (it.context ? `<span class="v4-cm-tag">${escapeAttr(it.context)}</span>` : "") +
                  `<span class="v4-cm-tag">档位 ${escapeAttr(effRange)}</span>` +
                  subPill +
                `</div>` +
                (it.note ? `<div class="v4-cm-note">${escapeAttr(it.note)}</div>` : "") +
              `</button>`
            );
          })
          .join("");
        return `<div class="v4-cascade-subgroup"><div class="v4-cascade-sg-title">${escapeAttr(sg.label)}</div>${rowsHtml}</div>`;
      })
      .join("");

    itemsCol.querySelectorAll("[data-cascade-model]").forEach((mBtn) => {
      mBtn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const chosenModel = mBtn.dataset.cascadeModel || "";
        const chosenDrv = mBtn.dataset.cascadeDrv || "";
        closeCascadePickers();
        if (typeof onSelectModel === "function") {
          onSelectModel(chosenModel, chosenDrv);
        }
      });
    });
  };

  renderColumns();

  trigBtn?.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const willOpen = !containerEl.classList.contains("is-open");
    closeCascadePickers(willOpen ? containerEl : null);
    containerEl.classList.toggle("is-open", willOpen);
    popEl.classList.toggle("hidden", !willOpen);
    trigBtn.setAttribute("aria-expanded", willOpen ? "true" : "false");
    if (willOpen) {
      renderColumns();
      activeFloatingEntry = { wrap: containerEl, trigger: trigBtn, menu: popEl, kind: "cascade" };
      positionFloatingLayer(trigBtn, popEl, "cascade");
      setTimeout(() => searchInp?.focus(), 20);
    }
  });
  popEl.addEventListener("click", (ev) => ev.stopPropagation());
  searchInp?.addEventListener("input", () => {
    renderColumns();
    positionFloatingLayer(trigBtn, popEl, "cascade");
  });
  searchInp?.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      ev.stopPropagation();
      closeCascadePickers();
    }
  });
}

export function enhanceGlassSelects(rootEl = document) {
  const scope = rootEl || document;
  scope.querySelectorAll("select.select-input:not(.hidden)").forEach((sel) => {
    let wrap = sel.parentElement?.classList.contains("v4-glass-select-wrap") ? sel.parentElement : null;
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "v4-glass-select-wrap";
      sel.parentNode?.insertBefore(wrap, sel);
      wrap.appendChild(sel);
      sel.classList.add("v4-select-native-sr");
      const trig = document.createElement("button");
      trig.type = "button";
      trig.className = "v4-glass-select-trigger";
      trig.setAttribute("aria-haspopup", "listbox");
      trig.setAttribute("aria-expanded", "false");
      wrap.appendChild(trig);

      const menu = document.createElement("div");
      menu.className = "v4-glass-select-menu hidden";
      menu.setAttribute("role", "listbox");
      getFloatingPortalHost().appendChild(menu);
      floatingMenuByWrap.set(wrap, menu);

      trig.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (sel.disabled) return;
        const willOpen = !wrap.classList.contains("is-open");
        closeCascadePickers(willOpen ? wrap : null);
        syncSingleGlassSelect(sel);
        wrap.classList.toggle("is-open", willOpen);
        menu.classList.toggle("hidden", !willOpen);
        trig.setAttribute("aria-expanded", willOpen ? "true" : "false");
        if (willOpen) {
          activeFloatingEntry = { wrap, trigger: trig, menu, kind: "select" };
          positionFloatingLayer(trig, menu, "select");
        }
      });
      menu.addEventListener("click", (ev) => ev.stopPropagation());
      sel.addEventListener("change", () => syncSingleGlassSelect(sel));
    }
    syncSingleGlassSelect(sel);
  });
}

function syncSingleGlassSelect(sel) {
  const wrap = sel?.parentElement;
  if (!wrap || !wrap.classList.contains("v4-glass-select-wrap")) return;
  const trig = wrap.querySelector(".v4-glass-select-trigger");
  const menu = floatingMenuByWrap.get(wrap);
  if (!trig || !menu) return;
  const opts = Array.from(sel.options);
  const activeOpt = opts.find((o) => o.value === sel.value) || opts[sel.selectedIndex] || opts[0];
  trig.disabled = Boolean(sel.disabled);
  trig.title = activeOpt?.textContent || "";
  trig.innerHTML =
    `<span class="v4-gs-label">${escapeAttr(activeOpt?.textContent || "")}</span>` +
    `${LINEAR_UI_ICONS.chevronDown}`;
  menu.innerHTML = opts
    .map((o) => {
      const isSel = o.value === (activeOpt?.value ?? "");
      return (
        `<button type="button" class="v4-glass-select-opt${isSel ? " selected" : ""}" data-gs-val="${escapeAttr(o.value)}">` +
          `<span class="v4-gs-opt-text">${escapeAttr(o.textContent || "")}</span>` +
          (isSel ? `<span class="v4-gs-chk">${LINEAR_UI_ICONS.check}</span>` : "") +
        `</button>`
      );
    })
    .join("");
  menu.querySelectorAll("[data-gs-val]").forEach((btn) => {
    btn.onclick = (ev) => {
      ev.stopPropagation();
      const val = btn.dataset.gsVal ?? "";
      if (sel.value !== val) {
        sel.value = val;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      }
      closeCascadePickers();
      syncSingleGlassSelect(sel);
    };
  });
}

export function renderSubscriptionControlsInModal() {
  const segBox = $id("cfgSubTierSeg");
  const hintEl = $id("cfgSubTierHint");
  const vendorGrid = $id("cfgVendorSubGrid");
  const jumpSubBtn = $id("cfgSeatsJumpSubBtn");

  const cat = getCatalogRoot();
  const st = storeBridge.state || {};
  const curTier = String(st.subscriptionTier || st.system?.subscription_tier || "all").toLowerCase();
  const vendorSubs = st.vendorSubscriptions || st.system?.vendor_subscriptions || {};
  const vendorCount = Object.values(vendorSubs).filter((v) => v && v !== "auto").length;

  if (jumpSubBtn) {
    const shortTier = cat.subscription_tiers?.[curTier]?.short_label || "全部";
    const suffix = vendorCount > 0 ? ` + ${vendorCount} 厂商混订` : "";
    const spanEl = jumpSubBtn.querySelector("span");
    if (spanEl) spanEl.textContent = `订阅：${shortTier}${suffix} · 切换方案`;
  }

  if (!segBox) return;
  segBox.querySelectorAll("[data-sub-tier]").forEach((pill) => {
    const tKey = pill.dataset.subTier;
    pill.classList.toggle("active", tKey === curTier);
    pill.onclick = () => {
      if (storeBridge.state) storeBridge.state.subscriptionTier = tKey;
      renderSubscriptionControlsInModal();
      refreshAllModalSeatChips();
    };
  });

  if (hintEl) {
    const tDesc = cat.subscription_tiers?.[curTier]?.desc;
    hintEl.textContent = tDesc || "展示全目录模型与完整推理档位";
  }

  if (vendorGrid) {
    const vendorPlans = cat.vendor_plans || {};
    const entries = Object.entries(vendorPlans);
    if (entries.length > 0) {
      vendorGrid.querySelectorAll("select[data-vendor-sub-drv]").forEach((oldSel) => {
        const oldWrap = oldSel.parentElement;
        const oldMenu = oldWrap ? floatingMenuByWrap.get(oldWrap) : null;
        if (oldMenu && oldMenu.parentNode) oldMenu.remove();
      });
      vendorGrid.innerHTML = entries
        .map(([dk, vInfo]) => {
          const curPlan = vendorSubs[dk] || "auto";
          const optsHtml = (vInfo.plans || [])
            .map(
              (p) =>
                `<option value="${escapeAttr(p.key)}"${p.key === curPlan ? " selected" : ""}>${escapeAttr(p.label)}</option>`
            )
            .join("");
          return (
            `<div class="v4-vendor-sub-item">` +
              `<label>${escapeAttr(vInfo.provider || dk.toUpperCase())}</label>` +
              `<select class="select-input" data-vendor-sub-drv="${escapeAttr(dk)}">${optsHtml}</select>` +
            `</div>`
          );
        })
        .join("");

      vendorGrid.querySelectorAll("[data-vendor-sub-drv]").forEach((vSel) => {
        vSel.addEventListener("change", () => {
          if (!storeBridge.state) return;
          if (!storeBridge.state.vendorSubscriptions) storeBridge.state.vendorSubscriptions = {};
          const dk = vSel.dataset.vendorSubDrv;
          const val = vSel.value || "auto";
          if (val === "auto") {
            delete storeBridge.state.vendorSubscriptions[dk];
          } else {
            storeBridge.state.vendorSubscriptions[dk] = val;
          }
          renderSubscriptionControlsInModal();
          refreshAllModalSeatChips();
        });
      });
      enhanceGlassSelects(vendorGrid);
    }
  }
}

export function alignModalSeatsToSubscription() {
  const cat = getCatalogRoot();
  const driversMap = cat.drivers || {};
  let alignedCount = 0;

  SEAT_CAPS.forEach((cap) => {
    const drvSel = $id(`cfg${cap}Driver`);
    const modelInp = $id(`cfg${cap}Model`);
    const discSel = $id(`cfg${cap}Effort`);
    const execSel = $id(`cfg${cap}ExecEffort`);
    if (!drvSel || !modelInp) return;

    const drv = drvSel.value || "auto";
    if (drv === "auto" || !driversMap[drv]) return;
    const dEntry = driversMap[drv];
    const modelsObj = dEntry.models || {};
    const curModel = modelInp.value.trim().toLowerCase();
    const curFit = curModel && modelsObj[curModel] ? evaluateModelSubscriptionFit(drv, curModel, modelsObj[curModel]) : { unlocked: false };

    let targetModel = modelInp.value.trim();
    if (!curModel || !curFit.unlocked) {
      const allConcrete = Object.keys(modelsObj).filter(
        (k) => k && !k.includes("*") && !k.startsWith("gemini-pro-orchestrator")
      );
      const unlockedCands = allConcrete.filter((k) => evaluateModelSubscriptionFit(drv, k, modelsObj[k]).unlocked);
      const recUnlocked = (dEntry.recommended_models || []).find((rk) => {
        const rkId = typeof rk === "string" ? rk : rk?.value;
        return rkId && unlockedCands.includes(rkId.toLowerCase());
      });
      targetModel = (typeof recUnlocked === "string" ? recUnlocked : recUnlocked?.value) || unlockedCands[0] || dEntry.default_model || targetModel;
      if (targetModel && targetModel !== modelInp.value.trim()) {
        modelInp.value = targetModel;
        modelInp.dispatchEvent(new Event("input", { bubbles: true }));
        alignedCount += 1;
      }
    }

    const mLow = (modelInp.value || "").trim().toLowerCase();
    const fitNow = evaluateModelSubscriptionFit(drv, mLow, modelsObj[mLow]);
    if (fitNow.effortCap && discSel && !discSel.disabled) {
      const allowedOpts = Array.from(discSel.options).map((o) => o.value).filter(Boolean);
      const withinCap = allowedOpts.filter((lv) => !isEffortAboveSubscriptionCap(lv, fitNow.effortCap));
      if (withinCap.length > 0 && isEffortAboveSubscriptionCap(discSel.value, fitNow.effortCap)) {
        const cappedVal = withinCap[withinCap.length - 1];
        discSel.value = cappedVal;
        discSel.dispatchEvent(new Event("change", { bubbles: true }));
        if (execSel && !execSel.disabled && Array.from(execSel.options).some((o) => o.value === cappedVal)) {
          execSel.value = cappedVal;
        }
        alignedCount += 1;
      }
    }
    renderSeatModelAndEffortChips(cap);
  });

  notifyToast(
    alignedCount > 0
      ? `已按当前订阅档位为 ${alignedCount} 项席位参数对齐免超限模型与推理档位`
      : "当前各席位模型与推理档位均已在所选订阅档位范围内",
    "ok"
  );
}

function buildDynamicModelChipsForDriver(driverKey) {
  const catalog = getCatalogRoot();
  const driversMap = catalog?.drivers || {};
  const drv = String(driverKey || "auto").toLowerCase();

  if (drv !== "auto" && driversMap[drv]) {
    const dEntry = driversMap[drv];
    const modelsObj = dEntry.models || {};
    if (Array.isArray(dEntry.recommended_models) && dEntry.recommended_models.length > 0) {
      return dEntry.recommended_models.map((item) => {
        const val = typeof item === "string" ? item : String(item.value || item.id || "");
        const mSpec = modelsObj[val.toLowerCase()] || modelsObj[val] || {};
        const fit = evaluateModelSubscriptionFit(drv, val, mSpec);
        return {
          value: val,
          label: formatModelShortLabel(val, typeof item === "object" ? item.label : mSpec.label || ""),
          unlocked: fit.unlocked,
          requiredBadge: fit.requiredBadge,
        };
      });
    }
    const concreteKeys = Object.keys(modelsObj).filter(
      (k) =>
        k &&
        !k.includes("*") &&
        !k.includes("(") &&
        !k.startsWith("gemini-pro-orchestrator") &&
        modelsObj[k]?.supports_effort !== false
    );
    if (concreteKeys.length > 0) {
      return concreteKeys.slice(0, 4).map((k) => {
        const fit = evaluateModelSubscriptionFit(drv, k, modelsObj[k]);
        return {
          value: k,
          label: formatModelShortLabel(k, modelsObj[k]?.label || ""),
          unlocked: fit.unlocked,
          requiredBadge: fit.requiredBadge,
        };
      });
    }
  }

  const autoChips = [{ value: "", label: "跟随驱动默认", unlocked: true }];
  const seen = new Set([""]);
  for (const dk of Object.keys(driversMap)) {
    const defModel = String(driversMap[dk]?.default_model || "").trim();
    if (defModel && !seen.has(defModel)) {
      seen.add(defModel);
      autoChips.push({ value: defModel, label: formatModelShortLabel(defModel), unlocked: true });
    }
  }
  return autoChips;
}

export function renderSeatModelAndEffortChips(seatCap) {
  const drvSel = $id(`cfg${seatCap}Driver`);
  const modelInp = $id(`cfg${seatCap}Model`);
  const cascadeWrap = $id(`v4CascadeWrap${seatCap}`);
  const chipBar = $id(`v4ModelChips${seatCap}`);
  const discSel = $id(`cfg${seatCap}Effort`);
  const execSel = $id(`cfg${seatCap}ExecEffort`);
  const effortSeg = $id(`v4EffortSeg${seatCap}`);
  if (!drvSel || !modelInp || !chipBar || !discSel || !effortSeg) return;

  const drv = drvSel.value || "auto";
  const curModel = modelInp.value.trim();

  if (cascadeWrap) {
    renderCascadingModelWidget(cascadeWrap, {
      driverKey: drv,
      currentModel: curModel,
      onSelectModel: (chosenModel, chosenDrv) => {
        if (drv === "auto" && chosenDrv && chosenDrv !== "auto" && Array.from(drvSel.options).some((o) => o.value === chosenDrv)) {
          drvSel.value = chosenDrv;
          drvSel.dispatchEvent(new Event("change", { bubbles: true }));
        }
        modelInp.value = chosenModel;
        modelInp.dispatchEvent(new Event("input", { bubbles: true }));
        modelInp.dispatchEvent(new Event("change", { bubbles: true }));
        setTimeout(() => renderSeatModelAndEffortChips(seatCap), 20);
      },
    });
  }

  const baseChips = buildDynamicModelChipsForDriver(drv);
  const chips = [...baseChips];
  const matchesPreset = chips.some((c) => c.value.toLowerCase() === curModel.toLowerCase());
  if (curModel && !matchesPreset) {
    const curMeta = lookupModelDisplayMeta(drv, curModel);
    chips.push({
      value: curModel,
      label: curMeta.shortLabel || curModel,
      unlocked: curMeta.unlocked,
      requiredBadge: curMeta.requiredBadge,
      isDynamicCurrent: true,
    });
  }

  chipBar.innerHTML = chips
    .map((c) => {
      const isAct =
        c.value.toLowerCase() === curModel.toLowerCase() || (!curModel && chips[0] && c.value === chips[0].value);
      const lockCls = c.unlocked === false ? " chip-above-tier" : "";
      const titleTxt = c.unlocked === false ? `需 ${c.requiredBadge || "高阶"} 订阅或 API` : c.value || "跟随驱动默认";
      return `<button type="button" class="v4-model-chip${isAct ? " active" : ""}${lockCls}" data-chip-model="${escapeAttr(c.value)}" title="${escapeAttr(titleTxt)}">${escapeAttr(c.label)}</button>`;
    })
    .join("");

  chipBar.querySelectorAll("[data-chip-model]").forEach((btn) => {
    btn.onclick = () => {
      modelInp.value = btn.dataset.chipModel || "";
      modelInp.dispatchEvent(new Event("input", { bubbles: true }));
      modelInp.dispatchEvent(new Event("change", { bubbles: true }));
      setTimeout(() => renderSeatModelAndEffortChips(seatCap), 20);
    };
  });

  const curMetaForEff = lookupModelDisplayMeta(drv, curModel);
  const effCap = curMetaForEff.effortCap || "";

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
      .map((o) => {
        const overCap = isEffortAboveSubscriptionCap(o.value, effCap);
        const tip = overCap ? `当前订阅建议上限为 ${effCap}（仍可手动指定）` : `推理档位 ${o.value}`;
        return `<button type="button" class="v4-effort-pill-btn${o.value === activeVal ? " active" : ""}${overCap ? " pill-above-cap" : ""}" data-eff-val="${escapeAttr(
          o.value
        )}" title="${escapeAttr(tip)}">${escapeAttr(o.value)}</button>`;
      })
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
  const modal = $id("settingsModal");
  if (modal) enhanceGlassSelects(modal);
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
  closeCascadePickers();
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
      window.dispatchEvent(new CustomEvent("roundtable:expand-composer", { detail: { focus: false } }));
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
  $id("railAttachQuickBtn")?.addEventListener("click", () => {
    window.dispatchEvent(new CustomEvent("roundtable:expand-composer", { detail: { focus: false } }));
    fileInp?.click();
  });

  fileInp?.addEventListener("change", async () => {
    if (fileInp.files?.length) {
      window.dispatchEvent(new CustomEvent("roundtable:expand-composer", { detail: { focus: false } }));
      await handleSelectedFiles(fileInp.files);
      fileInp.value = "";
    }
  });
  imgInp?.addEventListener("change", async () => {
    if (imgInp.files?.length) {
      window.dispatchEvent(new CustomEvent("roundtable:expand-composer", { detail: { focus: false } }));
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
      window.dispatchEvent(new CustomEvent("roundtable:expand-composer", { detail: { focus: false } }));
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
    window.dispatchEvent(new CustomEvent("roundtable:expand-composer", { detail: { focus: false } }));
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

  $id("settingsModal")?.addEventListener("roundtable:settings-open", () => {
    renderSubscriptionControlsInModal();
    refreshAllModalSeatChips();
  });
  $id("cfgAlignSubBtn")?.addEventListener("click", () => alignModalSeatsToSubscription());
  window.addEventListener("resize", () => repositionActiveFloatingLayer());
  document.addEventListener(
    "scroll",
    (ev) => {
      if (!activeFloatingEntry) return;
      if (activeFloatingEntry.menu.contains(ev.target)) return;
      repositionActiveFloatingLayer();
    },
    true
  );

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

  initTopicTitlePopover();
  initV5KineticStageAndSpotlight();
}

function initTopicTitlePopover() {
  const heading = $id("currentTopicTitle");
  if (!heading || heading.dataset.popoverBound === "1") return;
  heading.dataset.popoverBound = "1";

  const pop = document.createElement("div");
  pop.id = "v4TopicTitlePopover";
  pop.className = "v4-topic-tooltip-popover hidden";
  pop.setAttribute("role", "tooltip");
  getFloatingPortalHost().appendChild(pop);

  let showTimer = 0;
  let hideTimer = 0;
  let pinnedByClick = false;

  const getTitlePayload = () => {
    const dispTitle = (heading.dataset.fullTitle || heading.textContent || "").trim();
    const fullTopic = (heading.dataset.fullTopic || dispTitle).trim();
    const isTruncated = heading.scrollWidth > heading.clientWidth + 1;
    const hasExtraTopic = Boolean(fullTopic && fullTopic !== dispTitle);
    return { dispTitle, fullTopic, isTruncated, hasExtraTopic };
  };

  const syncCueClass = () => {
    const { dispTitle, isTruncated, hasExtraTopic } = getTitlePayload();
    const active = Boolean(dispTitle && (isTruncated || hasExtraTopic));
    heading.classList.toggle("has-topic-popover", active);
  };

  const positionPopover = () => {
    const rect = heading.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      hidePopover(true);
      return;
    }
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const margin = 14;
    const popW = Math.min(pop.offsetWidth || 340, vw - margin * 2);
    const left = Math.min(Math.max(margin, rect.left), Math.max(margin, vw - popW - margin));
    pop.style.left = `${Math.round(left)}px`;
    const top = Math.min(rect.bottom + 8, vh - 120);
    pop.style.top = `${Math.round(Math.max(margin, top))}px`;
  };

  const renderPopoverContent = ({ dispTitle, fullTopic, hasExtraTopic }) => {
    const copyText = hasExtraTopic ? fullTopic : dispTitle;
    pop.innerHTML =
      `<div class="v4-topic-tip-head">` +
        `<span class="v4-topic-tip-label">${hasExtraTopic ? "会议全称与完整议题" : "会议全称"}</span>` +
        `<button type="button" class="v4-topic-tip-copy" data-topic-copy="1">${LINEAR_UI_ICONS.copy}<span>复制</span></button>` +
      `</div>` +
      `<div class="v4-topic-tip-title">${escapeAttr(dispTitle)}</div>` +
      (hasExtraTopic
        ? `<div class="v4-topic-tip-full-wrap">` +
            `<span class="v4-topic-tip-label">完整议题</span>` +
            `<div class="v4-topic-tip-full">${escapeAttr(fullTopic)}</div>` +
          `</div>`
        : "");

    const copyBtn = pop.querySelector("[data-topic-copy]");
    copyBtn?.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      try {
        await navigator.clipboard.writeText(copyText);
        notifyToast("会议全称已复制", "ok");
      } catch {
        const ta = document.createElement("textarea");
        ta.value = copyText;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
        notifyToast("会议全称已复制", "ok");
      }
    });
  };

  const showPopover = (force = false) => {
    clearTimeout(hideTimer);
    clearTimeout(showTimer);
    const payload = getTitlePayload();
    if (!payload.dispTitle) return;
    if (!force && !payload.isTruncated && !payload.hasExtraTopic) return;
    renderPopoverContent(payload);
    pop.classList.remove("hidden");
    positionPopover();
  };

  const hidePopover = (immediate = false) => {
    clearTimeout(showTimer);
    clearTimeout(hideTimer);
    if (immediate) {
      pinnedByClick = false;
      pop.classList.add("hidden");
      return;
    }
    hideTimer = window.setTimeout(() => {
      if (!pinnedByClick) {
        pop.classList.add("hidden");
      }
    }, 170);
  };

  heading.addEventListener("mouseenter", () => {
    clearTimeout(hideTimer);
    syncCueClass();
    showTimer = window.setTimeout(() => showPopover(false), 110);
  });

  heading.addEventListener("mouseleave", () => {
    clearTimeout(showTimer);
    hidePopover(false);
  });

  heading.addEventListener("focus", () => {
    syncCueClass();
    showPopover(false);
  });

  heading.addEventListener("blur", () => {
    hidePopover(false);
  });

  heading.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const isHidden = pop.classList.contains("hidden");
    if (isHidden) {
      pinnedByClick = true;
      showPopover(true);
    } else {
      hidePopover(true);
    }
  });

  pop.addEventListener("mouseenter", () => {
    clearTimeout(hideTimer);
  });

  pop.addEventListener("mouseleave", () => {
    hidePopover(false);
  });

  pop.addEventListener("click", (ev) => ev.stopPropagation());

  document.addEventListener("click", () => {
    if (!pop.classList.contains("hidden")) {
      hidePopover(true);
    }
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !pop.classList.contains("hidden")) {
      hidePopover(true);
    }
  });

  window.addEventListener("resize", () => {
    syncCueClass();
    if (!pop.classList.contains("hidden")) {
      positionPopover();
    }
  });

  window.addEventListener("roundtable:topic-title-updated", () => {
    requestAnimationFrame(syncCueClass);
    if (!pop.classList.contains("hidden")) {
      showPopover(pinnedByClick);
    }
  });

  requestAnimationFrame(syncCueClass);
}

/* ==================== v5.5 第一版横贯基因 · 8横2纵丝线 · 108颗12种镂空物种 · 240px蛛网与0.80×零跳变真丝引擎 ==================== */

const MOTION_STORAGE_KEY = "ai_rt_motion";
const SPOTLIGHT_SELECTOR =
  ".msg-card, .seat-card, .intent-pack-card, .scenario-preset-card, .wb-card, .wb-pool-item, .workspace-card, .session-item, .cli-card, .agent-cfg-box, .rail-icon-btn, .v4-composer-dock, .compact-composer-bar, .compact-ring-summary, .stage-fold-group, .v4-cascade-trigger, .v4-glass-select-trigger, .v4-sub-tier-pill";

function parseCssColorToRgb(rawColor, fallback = [124, 113, 245]) {
  const s = String(rawColor || "").trim();
  if (!s) return fallback;
  if (s.startsWith("#")) {
    const hex = s.slice(1);
    if (hex.length === 3) {
      return [
        parseInt(hex[0] + hex[0], 16),
        parseInt(hex[1] + hex[1], 16),
        parseInt(hex[2] + hex[2], 16),
      ];
    }
    if (hex.length >= 6) {
      return [
        parseInt(hex.slice(0, 2), 16),
        parseInt(hex.slice(2, 4), 16),
        parseInt(hex.slice(4, 6), 16),
      ];
    }
  }
  const m = s.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i);
  if (m) {
    return [Number(m[1]), Number(m[2]), Number(m[3])];
  }
  return fallback;
}

function rgbaStr(rgb, alpha) {
  const a = Math.max(0, Math.min(1, alpha));
  return `rgba(${Math.round(rgb[0])}, ${Math.round(rgb[1])}, ${Math.round(rgb[2])}, ${a.toFixed(3)})`;
}

function drawCurvedFourStar(ctx, cx, cy, arm, pinch = 0.23, rot = 0) {
  ctx.save();
  ctx.translate(cx, cy);
  if (rot) ctx.rotate(rot);
  const k = arm * pinch;
  ctx.beginPath();
  ctx.moveTo(0, -arm);
  ctx.quadraticCurveTo(k, -k, arm, 0);
  ctx.quadraticCurveTo(k, k, 0, arm);
  ctx.quadraticCurveTo(-k, k, -arm, 0);
  ctx.quadraticCurveTo(-k, -k, 0, -arm);
  ctx.closePath();
  ctx.restore();
}

function drawMiniGuillocheTrefoil(ctx, cx, cy, scaleR, rotAngle) {
  const steps = 36;
  ctx.beginPath();
  for (let s = 0; s <= steps; s++) {
    const t = (s / steps) * Math.PI * 2;
    const r = scaleR * (0.74 + 0.28 * Math.cos(3 * t));
    const phi = 2 * t + rotAngle;
    const px = cx + r * Math.cos(phi);
    const py = cy + r * Math.sin(phi);
    if (s === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
}

function drawRegularPolygon(ctx, cx, cy, r, sides, rot = 0) {
  ctx.beginPath();
  for (let i = 0; i < sides; i++) {
    const a = rot + (i / sides) * Math.PI * 2;
    const px = cx + Math.cos(a) * r;
    const py = cy + Math.sin(a) * r;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
}

function drawHollowFloaterSpecies(ctx, p, radius, rgb, alpha, breathe, rotNow, isCalm) {
  const shape = p.shape;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  if (shape === "double-ring") {
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius * 1.08, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.86);
    ctx.lineWidth = 1.15;
    ctx.stroke();

    const outerR = radius * (1.96 - breathe * 0.22);
    ctx.beginPath();
    ctx.arc(p.x, p.y, outerR, rotNow * 0.5, rotNow * 0.5 + Math.PI * 1.65);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.36);
    ctx.lineWidth = 0.82;
    ctx.stroke();

    const satAng = rotNow * 1.65;
    ctx.beginPath();
    ctx.arc(p.x + Math.cos(satAng) * outerR, p.y + Math.sin(satAng) * outerR, 1.25, 0, Math.PI * 2);
    ctx.fillStyle = rgbaStr(rgb, alpha * 0.9);
    ctx.fill();
  } else if (shape === "star4") {
    const arm = radius * (1.56 + breathe * 0.3);
    if (breathe > 0.42) {
      const sGlow = ctx.createRadialGradient(p.x, p.y, 0.4, p.x, p.y, arm * 1.55);
      sGlow.addColorStop(0, rgbaStr(rgb, alpha * 0.24));
      sGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = sGlow;
      ctx.beginPath();
      ctx.arc(p.x, p.y, arm * 1.55, 0, Math.PI * 2);
      ctx.fill();
    }
    drawCurvedFourStar(ctx, p.x, p.y, arm, 0.21, rotNow * 0.35);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.9);
    ctx.lineWidth = 1.08;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(p.x, p.y, radius * 0.28, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.56);
    ctx.lineWidth = 0.78;
    ctx.stroke();
  } else if (shape === "crescent") {
    const cr = radius * 1.4;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(rotNow * 0.42);
    ctx.beginPath();
    ctx.arc(0, 0, cr, -Math.PI * 0.68, Math.PI * 0.68, false);
    ctx.quadraticCurveTo(cr * 0.26, 0, Math.cos(-Math.PI * 0.68) * cr, Math.sin(-Math.PI * 0.68) * cr);
    ctx.closePath();
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.86);
    ctx.lineWidth = 1.1;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(cr * 0.58, 0, 1.15, 0, Math.PI * 2);
    ctx.fillStyle = rgbaStr(rgb, alpha * 0.84);
    ctx.fill();
    ctx.restore();
  } else if (shape === "saturn") {
    const sr = radius * 0.92;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(rotNow * 0.28 + 0.42);
    ctx.beginPath();
    ctx.arc(0, 0, sr, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.84);
    ctx.lineWidth = 1.08;
    ctx.stroke();

    const rx = sr * 2.18;
    const ry = sr * 0.64;
    ctx.beginPath();
    ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.7);
    ctx.lineWidth = 0.94;
    ctx.stroke();

    const mAng = rotNow * 1.8;
    ctx.beginPath();
    ctx.arc(Math.cos(mAng) * rx, Math.sin(mAng) * ry, 1.2, 0, Math.PI * 2);
    ctx.fillStyle = rgbaStr(rgb, alpha * 0.92);
    ctx.fill();
    ctx.restore();
  } else if (shape === "prism-tri") {
    const tr = radius * 1.5;
    drawRegularPolygon(ctx, p.x, p.y, tr, 3, rotNow * 0.55);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.84);
    ctx.lineWidth = 1.08;
    ctx.stroke();

    drawRegularPolygon(ctx, p.x, p.y, tr * 0.54, 3, -rotNow * 0.75 + Math.PI / 3);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.48);
    ctx.lineWidth = 0.84;
    ctx.stroke();
  } else if (shape === "hex-crystal") {
    const hr = radius * 1.36;
    drawRegularPolygon(ctx, p.x, p.y, hr, 6, rotNow * 0.4);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.82);
    ctx.lineWidth = 1.06;
    ctx.stroke();

    for (let hi = 0; hi < 3; hi++) {
      const ha = rotNow * 0.4 + (hi * Math.PI) / 3;
      ctx.beginPath();
      ctx.moveTo(p.x - Math.cos(ha) * hr * 0.72, p.y - Math.sin(ha) * hr * 0.72);
      ctx.lineTo(p.x + Math.cos(ha) * hr * 0.72, p.y + Math.sin(ha) * hr * 0.72);
      ctx.strokeStyle = rgbaStr(rgb, alpha * 0.34);
      ctx.lineWidth = 0.76;
      ctx.stroke();
    }

    ctx.beginPath();
    ctx.arc(p.x, p.y, hr * 0.32, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.56);
    ctx.lineWidth = 0.84;
    ctx.stroke();
  } else if (shape === "trefoil") {
    drawMiniGuillocheTrefoil(ctx, p.x, p.y, radius * 1.18, rotNow * 0.65);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.76);
    ctx.lineWidth = 1.02;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(p.x, p.y, radius * 0.28, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.48);
    ctx.lineWidth = 0.78;
    ctx.stroke();
  } else if (shape === "binary-orbit") {
    const br = radius * 1.34;
    const bAng = rotNow * 1.15;
    const x1 = p.x + Math.cos(bAng) * br;
    const y1 = p.y + Math.sin(bAng) * br;
    const x2 = p.x - Math.cos(bAng) * br * 0.82;
    const y2 = p.y - Math.sin(bAng) * br * 0.82;

    ctx.beginPath();
    ctx.arc(p.x, p.y, br * 0.92, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.26);
    ctx.lineWidth = 0.74;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.42);
    ctx.lineWidth = 0.78;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(x1, y1, radius * 0.52, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.88);
    ctx.lineWidth = 1.05;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(x2, y2, radius * 0.36, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.76);
    ctx.lineWidth = 0.9;
    ctx.stroke();
  } else if (shape === "compass") {
    const cRad = radius * 1.36;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(rotNow * 0.32);
    ctx.beginPath();
    ctx.arc(0, 0, cRad, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.48);
    ctx.lineWidth = 0.85;
    ctx.stroke();

    for (let ti = 0; ti < 4; ti++) {
      const ta = (ti * Math.PI) / 2;
      ctx.beginPath();
      ctx.moveTo(Math.cos(ta) * (cRad * 0.78), Math.sin(ta) * (cRad * 0.78));
      ctx.lineTo(Math.cos(ta) * (cRad * 1.24), Math.sin(ta) * (cRad * 1.24));
      ctx.strokeStyle = rgbaStr(rgb, alpha * 0.72);
      ctx.lineWidth = 0.9;
      ctx.stroke();
    }
    ctx.restore();

    drawCurvedFourStar(ctx, p.x, p.y, cRad * 0.88, 0.17, -rotNow * 0.45);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.88);
    ctx.lineWidth = 0.98;
    ctx.stroke();
  } else if (shape === "spiral-shell") {
    const spMax = radius * 1.56;
    const turns = Math.PI * 3.1;
    const spSteps = 22;
    ctx.beginPath();
    let tipX = p.x;
    let tipY = p.y;
    for (let si = 0; si <= spSteps; si++) {
      const su = si / spSteps;
      const st = su * turns + rotNow * 0.9;
      const sRad = radius * 0.16 + su * spMax;
      const sx = p.x + Math.cos(st) * sRad;
      const sy = p.y + Math.sin(st) * sRad;
      if (si === 0) ctx.moveTo(sx, sy);
      else ctx.lineTo(sx, sy);
      if (si === spSteps) {
        tipX = sx;
        tipY = sy;
      }
    }
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.78);
    ctx.lineWidth = 1.02;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(tipX, tipY, 1.2, 0, Math.PI * 2);
    ctx.fillStyle = rgbaStr(rgb, alpha * 0.9);
    ctx.fill();
  } else if (shape === "astrolabe-arc") {
    const ar = radius * 1.42;
    ctx.beginPath();
    ctx.arc(p.x, p.y, ar, rotNow * 0.7, rotNow * 0.7 + 1.85);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.82);
    ctx.lineWidth = 1.08;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(p.x, p.y, ar, rotNow * 0.7 + Math.PI, rotNow * 0.7 + Math.PI + 1.85);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.82);
    ctx.lineWidth = 1.08;
    ctx.stroke();

    const crossR = radius * 0.56;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(-rotNow * 0.5);
    ctx.beginPath();
    ctx.moveTo(-crossR, 0);
    ctx.lineTo(crossR, 0);
    ctx.moveTo(0, -crossR);
    ctx.lineTo(0, crossR);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.68);
    ctx.lineWidth = 0.92;
    ctx.stroke();
    ctx.restore();
  } else if (shape === "gyro-gimbal") {
    // 双轴陀螺仪星环：正交倾角椭圆双环动态进动 + 空心微轴核
    const gr = radius * 1.5;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(rotNow * 0.48);
    ctx.beginPath();
    ctx.ellipse(0, 0, gr, gr * (0.44 + breathe * 0.14), 0, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.84);
    ctx.lineWidth = 1.02;
    ctx.stroke();

    ctx.beginPath();
    ctx.ellipse(0, 0, gr * (0.46 + (1 - breathe) * 0.12), gr, Math.PI * 0.14, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.62);
    ctx.lineWidth = 0.88;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(0, 0, radius * 0.3, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.88);
    ctx.lineWidth = 0.9;
    ctx.stroke();
    ctx.restore();
  } else if (shape === "octa-diamond") {
    // 立体八面晶棱：修长空心菱形晶面 + 内部立体折线棱脊
    const dy = radius * (1.72 + breathe * 0.14);
    const dx = radius * 1.06;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(rotNow * 0.36);
    ctx.beginPath();
    ctx.moveTo(0, -dy);
    ctx.lineTo(dx, 0);
    ctx.lineTo(0, dy);
    ctx.lineTo(-dx, 0);
    ctx.closePath();
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.86);
    ctx.lineWidth = 1.06;
    ctx.stroke();

    const midOffset = dx * 0.36 * Math.sin(rotNow * 0.9);
    ctx.beginPath();
    ctx.moveTo(0, -dy);
    ctx.lineTo(midOffset, 0);
    ctx.lineTo(0, dy);
    ctx.moveTo(-dx, 0);
    ctx.lineTo(dx, 0);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.46);
    ctx.lineWidth = 0.8;
    ctx.stroke();
    ctx.restore();
  } else if (shape === "lotus-rosette") {
    // 六瓣旋轮镂空花窗：极坐标精密花瓣线刻
    const lr = radius * 1.46;
    const lSteps = 36;
    ctx.beginPath();
    for (let li = 0; li <= lSteps; li++) {
      const theta = (li / lSteps) * Math.PI * 2;
      const rho = lr * (0.52 + 0.48 * Math.abs(Math.cos(3 * theta)));
      const lx = p.x + Math.cos(theta + rotNow * 0.38) * rho;
      const ly = p.y + Math.sin(theta + rotNow * 0.38) * rho;
      if (li === 0) ctx.moveTo(lx, ly);
      else ctx.lineTo(lx, ly);
    }
    ctx.closePath();
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.78);
    ctx.lineWidth = 0.96;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(p.x, p.y, lr * 0.24, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.62);
    ctx.lineWidth = 0.82;
    ctx.stroke();
  } else if (shape === "lemniscate") {
    // 伯努利双纽流光环（∞ 空心细轨 + 巡游微珠）
    const infA = radius * 1.68;
    const infSteps = 28;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(rotNow * 0.34);
    ctx.beginPath();
    for (let ii = 0; ii <= infSteps; ii++) {
      const t = (ii / infSteps) * Math.PI * 2;
      const denom = 1 + Math.sin(t) * Math.sin(t);
      const ix = (infA * Math.cos(t)) / denom;
      const iy = (infA * 0.86 * Math.sin(t) * Math.cos(t)) / denom;
      if (ii === 0) ctx.moveTo(ix, iy);
      else ctx.lineTo(ix, iy);
    }
    ctx.closePath();
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.82);
    ctx.lineWidth = 1.02;
    ctx.stroke();

    const bt = rotNow * 1.9;
    const bDen = 1 + Math.sin(bt) * Math.sin(bt);
    ctx.beginPath();
    ctx.arc((infA * Math.cos(bt)) / bDen, (infA * 0.86 * Math.sin(bt) * Math.cos(bt)) / bDen, 1.15, 0, Math.PI * 2);
    ctx.fillStyle = rgbaStr(rgb, alpha * 0.92);
    ctx.fill();
    ctx.restore();
  } else if (shape === "hourglass-prism") {
    // 对顶双锥星漏：上下对称空心三角晶锥 + 腰部微星环
    const hy = radius * 1.54;
    const hx = radius * 1.04;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(rotNow * 0.4);
    ctx.beginPath();
    ctx.moveTo(-hx, -hy);
    ctx.lineTo(hx, -hy);
    ctx.lineTo(-hx, hy);
    ctx.lineTo(hx, hy);
    ctx.closePath();
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.82);
    ctx.lineWidth = 1.0;
    ctx.stroke();

    ctx.beginPath();
    ctx.ellipse(0, 0, hx * 0.68, radius * 0.32, 0, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.54);
    ctx.lineWidth = 0.8;
    ctx.stroke();
    ctx.restore();
  } else if (shape === "armillary-sphere") {
    // 浑天赤道星轨：外圈细赤道环 + 斜交黄道弦 + 双交点微珠
    const arR = radius * 1.44;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(rotNow * 0.3);
    ctx.beginPath();
    ctx.arc(0, 0, arR, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.72);
    ctx.lineWidth = 0.96;
    ctx.stroke();

    ctx.beginPath();
    ctx.ellipse(0, 0, arR, arR * 0.38, Math.PI * 0.24, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.62);
    ctx.lineWidth = 0.86;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(-arR, 0);
    ctx.lineTo(arR, 0);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.34);
    ctx.lineWidth = 0.72;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(arR, 0, 1.05, 0, Math.PI * 2);
    ctx.arc(-arR, 0, 1.05, 0, Math.PI * 2);
    ctx.fillStyle = rgbaStr(rgb, alpha * 0.88);
    ctx.fill();
    ctx.restore();
  } else {
    if (p.trail.length > 1 && !isCalm) {
      ctx.beginPath();
      ctx.moveTo(p.trail[0].x, p.trail[0].y);
      for (let tIdx = 1; tIdx < p.trail.length; tIdx++) {
        ctx.lineTo(p.trail[tIdx].x, p.trail[tIdx].y);
      }
      ctx.strokeStyle = rgbaStr(rgb, alpha * 0.38);
      ctx.lineWidth = radius * 0.82;
      ctx.stroke();
    }
    const cHead = radius * 1.08;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(rotNow * 0.7);
    ctx.beginPath();
    ctx.moveTo(0, -cHead);
    ctx.lineTo(cHead * 0.72, 0);
    ctx.lineTo(0, cHead);
    ctx.lineTo(-cHead * 0.72, 0);
    ctx.closePath();
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.88);
    ctx.lineWidth = 0.98;
    ctx.stroke();
    ctx.restore();

    ctx.beginPath();
    ctx.arc(p.x, p.y, radius * 1.78, 0, Math.PI * 2);
    ctx.strokeStyle = rgbaStr(rgb, alpha * 0.28);
    ctx.lineWidth = 0.75;
    ctx.stroke();
  }
}

function samplePolylineAt(pts, uNorm) {
  if (!pts || pts.length === 0) return { x: 0, y: 0 };
  if (pts.length === 1) return pts[0];
  const u = Math.max(0, Math.min(0.9999, uNorm));
  const scaled = u * (pts.length - 1);
  const idx = Math.floor(scaled);
  const frac = scaled - idx;
  const a = pts[idx];
  const b = pts[Math.min(pts.length - 1, idx + 1)];
  return {
    x: a.x + (b.x - a.x) * frac,
    y: a.y + (b.y - a.y) * frac,
  };
}

function evalCrossScreenStrandRest(st, u, tSec, width, height, motionScale, breatheScale) {
  const w1 = Math.sin(u * st.freq + tSec * st.speed * motionScale + st.phase);
  const w2 = Math.cos(u * st.freq * 1.61803 - tSec * st.speed * 0.79 * motionScale + st.phase * 1.73);
  const w3 = Math.sin(u * st.freq * 2.532 + tSec * st.speed * 0.53 * motionScale + st.phase * 2.61);
  const spatialEnv = 0.62 + 0.52 * Math.sin(u * Math.PI * 1.45 + st.phase * 0.82);
  const wave = st.amp * breatheScale * spatialEnv * (0.56 * w1 + 0.30 * w2 + 0.14 * w3);

  if (st.axis === "h") {
    const spanW = width + 80;
    const rx = -40 + u * spanW + st.amp * 0.22 * (0.65 * w2 - 0.35 * w3);
    const macroY =
      st.posRatio * height +
      st.slope * (u - 0.5) * height +
      st.arch1 * Math.sin(Math.PI * u) +
      st.arch2 * Math.sin(Math.PI * 2 * u + st.phase * 0.6);
    const ry = macroY + wave;
    const dydx =
      (st.slope * height + Math.PI * st.arch1 * Math.cos(Math.PI * u)) / Math.max(320, spanW);
    const invL = 1 / Math.sqrt(1 + dydx * dydx);
    return {
      x: rx,
      y: ry,
      tx: invL,
      ty: dydx * invL,
      nx: -dydx * invL,
      ny: invL,
    };
  }

  const spanH = height + 80;
  const ryV = -40 + u * spanH + st.amp * 0.22 * (0.65 * w2 - 0.35 * w3);
  const macroX =
    st.posRatio * width +
    st.slope * (u - 0.5) * width +
    st.arch1 * Math.sin(Math.PI * u) +
    st.arch2 * Math.sin(Math.PI * 2 * u + st.phase * 0.6);
  const rxV = macroX + wave;
  const dxdy =
    (st.slope * width + Math.PI * st.arch1 * Math.cos(Math.PI * u)) / Math.max(240, spanH);
  const invLV = 1 / Math.sqrt(1 + dxdy * dxdy);
  return {
    x: rxV,
    y: ryV,
    tx: dxdy * invLV,
    ty: invLV,
    nx: -invLV,
    ny: dxdy * invLV,
  };
}

function initV5KineticStageAndSpotlight() {
  const canvas = $id("v5KineticCanvas");
  if (!canvas || canvas.dataset.kineticBound === "1") return;
  canvas.dataset.kineticBound = "1";

  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  const reducedMotionMql = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : { matches: false };

  let motionMode = "vivid";
  try {
    const savedMotion = window.localStorage?.getItem(MOTION_STORAGE_KEY);
    if (savedMotion === "calm" || savedMotion === "vivid") {
      motionMode = savedMotion;
    }
  } catch {
    // ignore storage read error
  }

  const syncMotionModeUI = (nextMode) => {
    motionMode = nextMode === "calm" ? "calm" : "vivid";
    document.documentElement.setAttribute("data-motion", motionMode);
    try {
      window.localStorage?.setItem(MOTION_STORAGE_KEY, motionMode);
    } catch {
      // ignore storage write error
    }
    document.querySelectorAll("[data-motion-opt]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.motionOpt === motionMode);
    });
  };
  syncMotionModeUI(motionMode);

  document.querySelectorAll("[data-motion-opt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      syncMotionModeUI(btn.dataset.motionOpt);
      ensureLoopRunning();
    });
  });

  let width = Math.max(320, window.innerWidth || 1440);
  let height = Math.max(240, window.innerHeight || 900);
  let dpr = Math.min(2, window.devicePixelRatio || 1);

  // 二阶临界阻尼平滑指针追踪器（无瞬移速度尖峰，跟手灵敏）
  const pointer = {
    rawX: width * 0.52,
    rawY: height * 0.44,
    x: width * 0.52,
    y: height * 0.44,
    vx: 0,
    vy: 0,
    initialized: false,
    inside: false,
    presence: 0,
    energy: 0,
    trailCarry: 0,
  };

  let paletteColors = {
    isDark: false,
    accent: [85, 74, 224],
    carbon: [59, 99, 246],
    astra: [13, 148, 112],
    grok: [217, 119, 6],
    chair: [109, 40, 217],
    vega: [147, 51, 234],
    prism: [2, 132, 199],
  };

  const refreshThemePaletteColors = () => {
    const cs = window.getComputedStyle(document.documentElement);
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    paletteColors = {
      isDark,
      accent: parseCssColorToRgb(cs.getPropertyValue("--accent-primary"), isDark ? [147, 134, 255] : [85, 74, 224]),
      carbon: parseCssColorToRgb(cs.getPropertyValue("--carbon-color"), isDark ? [110, 168, 254] : [59, 99, 246]),
      astra: parseCssColorToRgb(cs.getPropertyValue("--astra-color"), isDark ? [52, 211, 153] : [13, 148, 112]),
      grok: parseCssColorToRgb(cs.getPropertyValue("--grok-color"), isDark ? [251, 191, 36] : [217, 119, 6]),
      chair: parseCssColorToRgb(cs.getPropertyValue("--chair-color"), isDark ? [196, 181, 253] : [109, 40, 217]),
      vega: parseCssColorToRgb(cs.getPropertyValue("--vega-color"), isDark ? [192, 132, 252] : [147, 51, 234]),
      prism: parseCssColorToRgb(cs.getPropertyValue("--prism-color"), isDark ? [56, 189, 248] : [2, 132, 199]),
    };
  };
  refreshThemePaletteColors();

  const resizeCanvas = () => {
    width = Math.max(320, window.innerWidth || 1440);
    height = Math.max(240, window.innerHeight || 900);
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  resizeCanvas();

  const COLOR_KEYS = ["accent", "carbon", "astra", "chair", "grok", "vega", "prism"];

  // 审定定版参数（博物丰盈升级：8横+2纵全屏不规则丝线、138颗/全18种精致“以线代面”镂空物种、298px等稳态加速磁吸与258px清透蛛网/132px星座连线）
  const HORIZ_STRAND_COUNT = 8;
  const VERT_STRAND_COUNT = 2;
  const RIBBON_NODE_COUNT = 58;
  const PARTICLE_COUNT = 138;
  const BOKEH_COUNT = 12;
  const CORRIDOR_BIAS = 0.36;
  const SILK_GAIN = 0.80;
  const SPIDER_RADIUS = 258;
  const CONSTELLATION_RADIUS = 132;
  const MAGNET_RADIUS = 298;

  const ALL_SPECIES = [
    "double-ring",
    "star4",
    "crescent",
    "saturn",
    "prism-tri",
    "hex-crystal",
    "trefoil",
    "binary-orbit",
    "comet",
    "compass",
    "spiral-shell",
    "astrolabe-arc",
    "gyro-gimbal",
    "octa-diamond",
    "lotus-rosette",
    "lemniscate",
    "hourglass-prism",
    "armillary-sphere",
  ];

  // 12 颗柔焦景深光斑（Bokeh Nebula Orbs）
  const bokehOrbs = Array.from({ length: BOKEH_COUNT }, (_, b) => {
    const u1 = ((b + 0.5) * 0.7548776662) % 1;
    const u2 = ((b + 0.5) * 0.569840291) % 1;
    const rx = b % 3 === 0 ? 0.05 + u1 * 0.19 : b % 3 === 1 ? 0.76 + u1 * 0.19 : 0.16 + u1 * 0.68;
    const ry = 0.07 + u2 * 0.86;
    return {
      x: rx * width,
      y: ry * height,
      vx: (((b * 37) % 100) / 100 - 0.5) * 0.15,
      vy: (((b * 53) % 100) / 100 - 0.5) * 0.13,
      baseR: 16 + (b % 4) * 4.8,
      colorKey: COLOR_KEYS[b % COLOR_KEYS.length],
      phase: b * 1.29,
      pulseSpeed: 0.44 + (b % 4) * 0.11,
    };
  });

  const baseRadiusForSpecies = (shape, i) => {
    if (shape === "trefoil" || shape === "lotus-rosette") return 4.5 + (i % 2) * 0.6;
    if (shape === "saturn" || shape === "gyro-gimbal" || shape === "armillary-sphere") return 3.6 + (i % 3) * 0.48;
    if (shape === "compass" || shape === "astrolabe-arc" || shape === "lemniscate") return 3.45 + (i % 2) * 0.52;
    if (shape === "double-ring" || shape === "binary-orbit" || shape === "hourglass-prism") return 3.25 + (i % 3) * 0.52;
    if (shape === "spiral-shell" || shape === "crescent" || shape === "octa-diamond") return 3.15 + (i % 3) * 0.48;
    if (shape === "star4" || shape === "prism-tri" || shape === "hex-crystal") return 3.0 + (i % 3) * 0.52;
    return 2.2 + (i % 3) * 0.4;
  };

  const seedParticlePosition = (idx) => {
    const g1 = ((idx + 1) * 0.7548776662466927) % 1;
    const g2 = ((idx + 1) * 0.5698402909980532) % 1;
    const detSlot = ((idx * 7 + 3) % 20) / 20;
    let nx;
    if (detSlot < CORRIDOR_BIAS * 0.5) {
      nx = 0.026 + g1 * 0.19;
    } else if (detSlot < CORRIDOR_BIAS) {
      nx = 0.784 + g1 * 0.19;
    } else {
      nx = 0.036 + g1 * 0.928;
    }
    const ny = 0.038 + g2 * 0.924;
    return { x: nx * width, y: ny * height };
  };

  // 138 颗全 18 种“以线代面”镂空几何漂浮物
  const particles = Array.from({ length: PARTICLE_COUNT }, (_, i) => {
    const shape = ALL_SPECIES[i % ALL_SPECIES.length];
    const pos = seedParticlePosition(i);
    return {
      x: pos.x,
      y: pos.y,
      vx: (((i * 73 + 19) % 100) / 100 - 0.5) * 0.34,
      vy: (((i * 41 + 67) % 100) / 100 - 0.5) * 0.32,
      baseR: baseRadiusForSpecies(shape, i),
      shape,
      colorKey: COLOR_KEYS[i % COLOR_KEYS.length],
      phase: (i * 1.47) % (Math.PI * 2),
      pulseSpeed: 0.82 + (i % 6) * 0.20,
      rotSpeed: (i % 2 === 0 ? 1 : -1) * (0.28 + (i % 5) * 0.11),
      driftSeed: i * 0.89,
      trail: [],
    };
  });

  // 8 条横穿全屏偏左右流向不规则丝线 + 2 条左右走廊纵向蜿蜒丝线
  const strands = [];
  for (let i = 0; i < HORIZ_STRAND_COUNT; i++) {
    const frac = i / (HORIZ_STRAND_COUNT - 1);
    const yRatio = 0.11 + frac * 0.78 + Math.sin(i * 2.1 + 0.4) * 0.028;
    const hSlope = (i % 2 === 0 ? 1 : -1) * (0.055 + ((i * 3) % 4) * 0.028);
    const hArch1 = (i % 2 === 0 ? 1 : -1) * (28 + (i % 3) * 15);
    const hArch2 = (i % 3 === 0 ? -1 : 1) * (16 + (i % 2) * 11);
    strands.push({
      axis: "h",
      posRatio: Math.max(0.07, Math.min(0.93, yRatio)),
      slope: hSlope,
      arch1: hArch1,
      arch2: hArch2,
      amp: 26 + (i % 4) * 6.5,
      freq: 4.4 + (i % 4) * 0.75,
      speed: (i % 2 === 0 ? 1 : -1) * (0.31 + (i % 4) * 0.065),
      phase: i * 1.37 + 0.3,
      colorKey: COLOR_KEYS[i % COLOR_KEYS.length],
      secondaryKey: COLOR_KEYS[(i + 2) % COLOR_KEYS.length],
      width: i % 3 === 0 ? 1.42 : 1.16,
      alpha: i % 3 === 0 ? 0.22 : 0.175,
      stiffScale: 0.92 + (i % 3) * 0.09,
      wakeScale: 1.0,
      smoothHover: 0,
      nodes: Array.from({ length: RIBBON_NODE_COUNT }, () => ({
        ox: 0,
        oy: 0,
        vx: 0,
        vy: 0,
      })),
    });
  }

  const vertPositions = [0.895, 0.098];
  for (let v = 0; v < VERT_STRAND_COUNT; v++) {
    strands.push({
      axis: "v",
      posRatio: vertPositions[v % vertPositions.length],
      slope: (v % 2 === 0 ? -1 : 1) * 0.068,
      arch1: (v % 2 === 0 ? 1 : -1) * 34,
      arch2: (v % 2 === 0 ? -1 : 1) * 18,
      amp: 26 + (v % 2) * 7,
      freq: 4.8 + v * 0.7,
      speed: (v % 2 === 0 ? 1 : -1) * (0.29 + v * 0.06),
      phase: 2.1 + v * 1.9,
      colorKey: COLOR_KEYS[(v + 2) % COLOR_KEYS.length],
      secondaryKey: COLOR_KEYS[(v + 5) % COLOR_KEYS.length],
      width: 1.14,
      alpha: 0.165,
      stiffScale: 0.95,
      wakeScale: 1.04,
      smoothHover: 0,
      nodes: Array.from({ length: RIBBON_NODE_COUNT }, () => ({
        ox: 0,
        oy: 0,
        vx: 0,
        vy: 0,
      })),
    });
  }

  // 沿丝线巡游的流光脉冲微珠
  const photonBeads = [];
  for (let sIdx = 0; sIdx < strands.length; sIdx++) {
    const st = strands[sIdx];
    photonBeads.push({
      strandIdx: sIdx,
      speed: (sIdx % 2 === 0 ? 1 : -1) * (0.032 + (sIdx % 4) * 0.007),
      offset: (sIdx * 0.19 + 0.09) % 1,
      radius: 1.95 + (sIdx % 3) * 0.42,
      colorKey: st.colorKey,
    });
    if (st.axis === "h" && sIdx % 3 === 0) {
      photonBeads.push({
        strandIdx: sIdx,
        speed: (sIdx % 2 === 0 ? 1 : -1) * (0.026 + (sIdx % 3) * 0.006),
        offset: (sIdx * 0.19 + 0.57) % 1,
        radius: 1.75,
        colorKey: st.secondaryKey,
      });
    }
  }

  const prevOxBuf = new Float32Array(RIBBON_NODE_COUNT);
  const prevOyBuf = new Float32Array(RIBBON_NODE_COUNT);

  const trailMotes = [];
  const clickWaves = [];

  const CLICK_EFFECT_TYPES = ["nova", "rosette", "orbit", "prism", "harmonic", "constellation"];
  let effectDeck = [];
  let lastEffectKind = "";
  const clickBursts = [];

  function drawNextClickEffectKind() {
    if (effectDeck.length === 0) {
      effectDeck = CLICK_EFFECT_TYPES.slice();
      for (let i = effectDeck.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        const tmp = effectDeck[i];
        effectDeck[i] = effectDeck[j];
        effectDeck[j] = tmp;
      }
      if (effectDeck[effectDeck.length - 1] === lastEffectKind && effectDeck.length > 1) {
        const swap = effectDeck[0];
        effectDeck[0] = effectDeck[effectDeck.length - 1];
        effectDeck[effectDeck.length - 1] = swap;
      }
    }
    const chosen = effectDeck.pop();
    lastEffectKind = chosen;
    return chosen;
  }

  function spawnRandomizedClickBurst(cx, cy) {
    const kind = drawNextClickEffectKind();
    const isCalm = motionMode === "calm";
    const scale = isCalm ? 0.72 : 1.0;
    const baseColorIdx = Math.floor(Math.random() * COLOR_KEYS.length);
    const primaryKey = COLOR_KEYS[baseColorIdx];
    const secondaryKey = COLOR_KEYS[(baseColorIdx + 2) % COLOR_KEYS.length];
    const tertiaryKey = COLOR_KEYS[(baseColorIdx + 4) % COLOR_KEYS.length];

    const burst = {
      kind,
      x: cx,
      y: cy,
      age: 0,
      duration:
        kind === "rosette"
          ? 1.2
          : kind === "constellation"
          ? 1.2
          : kind === "harmonic"
          ? 1.1
          : 1.05,
      scale,
      rot0: Math.random() * Math.PI * 2,
      primaryKey,
      secondaryKey,
      tertiaryKey,
      sparks: [],
      ticks: 20,
      tiltA: 0,
      tiltB: 1.18,
    };
    burst.tiltA = burst.rot0;
    burst.tiltB = burst.rot0 + Math.PI * 0.38;

    if (kind === "nova") {
      const n = isCalm ? 8 : 12;
      for (let i = 0; i < n; i++) {
        const ang = (i / n) * Math.PI * 2 + (Math.random() - 0.5) * 0.22;
        const spd = (74 + Math.random() * 64) * scale;
        burst.sparks.push({
          ang,
          spd,
          swirl: (i % 2 === 0 ? 1 : -1) * (1.1 + Math.random() * 0.7),
          r: 1.9 + Math.random() * 1.4,
          colorKey: COLOR_KEYS[(baseColorIdx + i) % COLOR_KEYS.length],
        });
      }
    } else if (kind === "rosette") {
      for (let i = 0; i < 8; i++) {
        burst.sparks.push({
          ang: (i / 8) * Math.PI * 2 + burst.rot0,
          dist: (54 + (i % 3) * 22) * scale,
          r: 2.4 + (i % 2) * 0.9,
          colorKey: COLOR_KEYS[(baseColorIdx + i) % COLOR_KEYS.length],
        });
      }
    } else if (kind === "orbit") {
      for (let i = 0; i < 6; i++) {
        burst.sparks.push({
          ringIdx: i % 2,
          phase0: (i / 3) * Math.PI * 2,
          omega: (i % 2 === 0 ? 1 : -1) * (4.0 + (i % 3) * 0.8),
          r: 2.2 + (i % 2) * 0.7,
          colorKey: COLOR_KEYS[(baseColorIdx + i) % COLOR_KEYS.length],
        });
      }
    } else if (kind === "prism") {
      const n = isCalm ? 7 : 10;
      for (let i = 0; i < n; i++) {
        const ang = (i / n) * Math.PI * 2 + (Math.random() - 0.5) * 0.35;
        const dist = (48 + Math.random() * 70) * scale;
        burst.sparks.push({
          dx: Math.cos(ang) * dist,
          dy: Math.sin(ang) * dist,
          floatY: -(16 + Math.random() * 24) * scale,
          sides: i % 3 === 0 ? 4 : i % 3 === 1 ? 6 : 3,
          r: (4.1 + (i % 3) * 1.4) * scale,
          rot0: Math.random() * Math.PI,
          rotSpd: (i % 2 === 0 ? 1 : -1) * (2.0 + Math.random() * 2.2),
          colorKey: COLOR_KEYS[(baseColorIdx + i) % COLOR_KEYS.length],
        });
      }
    } else if (kind === "constellation") {
      const n = isCalm ? 7 : 10;
      for (let i = 0; i < n; i++) {
        const ang = (i / n) * Math.PI * 2 + (Math.random() - 0.5) * 0.42;
        const dist = (38 + Math.random() * 72) * scale;
        burst.sparks.push({
          dx: Math.cos(ang) * dist,
          dy: Math.sin(ang) * dist,
          swirl: (Math.random() - 0.5) * 0.65,
          r: 2.2 + (i % 3) * 0.75,
          isStar: i % 3 === 0,
          colorKey: COLOR_KEYS[(baseColorIdx + i) % COLOR_KEYS.length],
        });
      }
    }

    clickBursts.push(burst);
    if (clickBursts.length > 6) clickBursts.shift();

    clickWaves.push({
      x: cx,
      y: cy,
      r: 12,
      maxR: (kind === "harmonic" ? 320 : 255) * scale,
      strength: (kind === "harmonic" ? 1.55 : 1.15) * Math.max(0.9, SILK_GAIN * 0.55) * scale,
      alpha: 1.0,
    });
    if (clickWaves.length > 4) clickWaves.shift();

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      const dx = p.x - cx;
      const dy = p.y - cy;
      const d = Math.hypot(dx, dy);
      if (d < 195) {
        const invD = 1 / Math.sqrt(d * d + 24 * 24);
        const kick = Math.pow(1 - d / 195, 2) * 1.65 * scale;
        p.vx += dx * invD * kick + -dy * invD * kick * 0.35;
        p.vy += dy * invD * kick + dx * invD * kick * 0.35;
      }
    }
  }

  let pendingSpotEvent = null;
  let spotRafId = 0;

  const flushSpotlightUpdate = () => {
    spotRafId = 0;
    if (!pendingSpotEvent) return;
    const { clientX, clientY, target } = pendingSpotEvent;
    pendingSpotEvent = null;
    if (!target || typeof target.closest !== "function") return;
    const hit = target.closest(SPOTLIGHT_SELECTOR);
    if (!hit) return;
    const rect = hit.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      const rx = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
      const ry = Math.max(0, Math.min(100, ((clientY - rect.top) / rect.height) * 100));
      hit.style.setProperty("--spot-x", `${rx.toFixed(1)}%`);
      hit.style.setProperty("--spot-y", `${ry.toFixed(1)}%`);
    }
  };

  window.addEventListener(
    "pointermove",
    (e) => {
      if (!pointer.initialized || (!pointer.inside && pointer.presence < 0.05)) {
        pointer.x = e.clientX;
        pointer.y = e.clientY;
        pointer.rawX = e.clientX;
        pointer.rawY = e.clientY;
        pointer.vx = 0;
        pointer.vy = 0;
        pointer.initialized = true;
      }

      const moveDist = Math.hypot(e.clientX - pointer.rawX, e.clientY - pointer.rawY);
      pointer.rawX = e.clientX;
      pointer.rawY = e.clientY;
      pointer.inside = true;
      pointer.energy = Math.min(1, pointer.energy + Math.min(0.30, moveDist * 0.015));

      if (!reducedMotionMql.matches && motionMode !== "calm" && moveDist > 3 && moveDist < 150) {
        pointer.trailCarry += moveDist;
        if (pointer.trailCarry >= 34) {
          pointer.trailCarry = 0;
          const cKey = COLOR_KEYS[Math.floor(Math.random() * COLOR_KEYS.length)];
          trailMotes.push({
            x: e.clientX + (Math.random() - 0.5) * 12,
            y: e.clientY + (Math.random() - 0.5) * 12,
            vx: (Math.random() - 0.5) * 0.55,
            vy: -0.30 - Math.random() * 0.45,
            r: 1.6 + Math.random() * 1.8,
            kind: Math.random() > 0.46 ? "star" : "ring",
            colorKey: cKey,
            life: 1.0,
            decay: 0.022 + Math.random() * 0.014,
            rot: Math.random() * Math.PI,
          });
          if (trailMotes.length > 18) trailMotes.shift();
        }
      }

      pendingSpotEvent = { clientX: e.clientX, clientY: e.clientY, target: e.target };
      if (!spotRafId) {
        spotRafId = requestAnimationFrame(flushSpotlightUpdate);
      }
    },
    { passive: true }
  );

  const handlePointerExit = () => {
    pointer.inside = false;
  };
  window.addEventListener("pointerleave", handlePointerExit, { passive: true });
  window.addEventListener("blur", handlePointerExit, { passive: true });

  window.addEventListener(
    "pointerdown",
    (e) => {
      if (reducedMotionMql.matches) return;
      spawnRandomizedClickBurst(e.clientX, e.clientY);
    },
    { passive: true }
  );

  window.addEventListener("resize", () => {
    const prevW = width;
    const prevH = height;
    resizeCanvas();
    if (prevW > 0 && prevH > 0) {
      const sx = width / prevW;
      const sy = height / prevH;
      for (const b of bokehOrbs) {
        b.x *= sx;
        b.y *= sy;
      }
      for (const p of particles) {
        p.x *= sx;
        p.y *= sy;
        p.trail.length = 0;
      }
      for (const st of strands) {
        for (const nd of st.nodes) {
          nd.ox *= sx;
          nd.oy *= sy;
        }
      }
    }
    if (reducedMotionMql.matches) {
      renderKineticFrame(performance.now() * 0.001, true);
    }
  });

  window.addEventListener("roundtable:appearance-changed", () => {
    refreshThemePaletteColors();
    if (reducedMotionMql.matches) {
      renderKineticFrame(performance.now() * 0.001, true);
    }
  });

  let lastFrameSec = performance.now() * 0.001;

  function renderKineticFrame(tSec, staticOnly = false) {
    const dt = Math.min(0.033, Math.max(0.004, tSec - lastFrameSec || 0.016));
    lastFrameSec = tSec;

    ctx.clearRect(0, 0, width, height);

    const isDark = paletteColors.isDark;
    const isCalm = motionMode === "calm" || staticOnly;
    const motionScale = staticOnly ? 0 : isCalm ? 0.42 : 1;
    const alphaBoost = isDark ? 1.30 : 1.04;
    const frameStep = dt * 60;

    // 0. 点击弹性波推进
    for (let wIdx = clickWaves.length - 1; wIdx >= 0; wIdx--) {
      const cw = clickWaves[wIdx];
      cw.r += (cw.maxR - cw.r) * (1 - Math.exp(-4.8 * dt)) + 105 * dt;
      cw.alpha *= Math.exp(-3.2 * dt);
      if (cw.alpha < 0.025 || cw.r >= cw.maxR) {
        clickWaves.splice(wIdx, 1);
      }
    }

    // 1. 高响应二阶临界阻尼连续指针追踪与极光光晕
    const targetPresence = pointer.inside && !staticOnly ? 1 : 0;
    pointer.presence += (targetPresence - pointer.presence) * (1 - Math.exp(-13.5 * dt));
    pointer.energy *= Math.exp((pointer.inside ? -1.85 : -5.0) * dt);

    if (!staticOnly) {
      const omega = 30.0;
      const ax = omega * omega * (pointer.rawX - pointer.x) - 2 * omega * pointer.vx;
      const ay = omega * omega * (pointer.rawY - pointer.y) - 2 * omega * pointer.vy;
      pointer.vx += ax * dt;
      pointer.vy += ay * dt;
      const maxPtrSpeed = 2600;
      const curSpd = Math.hypot(pointer.vx, pointer.vy);
      if (curSpd > 1) {
        const softScale = maxPtrSpeed / Math.hypot(curSpd, maxPtrSpeed);
        pointer.vx *= softScale;
        pointer.vy *= softScale;
      }
      pointer.x += pointer.vx * dt;
      pointer.y += pointer.vy * dt;
    }

    if (pointer.presence > 0.008 && !staticOnly) {
      const auraRadius = isCalm ? 165 : 265;
      const pEnv = pointer.presence * (0.62 + pointer.energy * 0.38);
      const auraGrad = ctx.createRadialGradient(pointer.x, pointer.y, 4, pointer.x, pointer.y, auraRadius);
      auraGrad.addColorStop(0, rgbaStr(paletteColors.accent, (isDark ? 0.16 : 0.105) * pEnv));
      auraGrad.addColorStop(0.45, rgbaStr(paletteColors.carbon, (isDark ? 0.085 : 0.052) * pEnv));
      auraGrad.addColorStop(0.78, rgbaStr(paletteColors.astra, (isDark ? 0.04 : 0.024) * pEnv));
      auraGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = auraGrad;
      ctx.beginPath();
      ctx.arc(pointer.x, pointer.y, auraRadius, 0, Math.PI * 2);
      ctx.fill();
    }

    // 1.5 柔焦景深光斑（Bokeh Orbs）
    const activeBokeh = isCalm ? Math.ceil(BOKEH_COUNT * 0.6) : BOKEH_COUNT;
    for (let bIdx = 0; bIdx < activeBokeh; bIdx++) {
      const b = bokehOrbs[bIdx];
      if (!staticOnly) {
        b.x += (b.vx + Math.cos(tSec * 0.24 + b.phase) * 0.10) * motionScale * frameStep;
        b.y += (b.vy + Math.sin(tSec * 0.20 + b.phase * 1.2) * 0.09) * motionScale * frameStep;
        if (b.x < -48) b.x = width + 48;
        else if (b.x > width + 48) b.x = -48;
        if (b.y < -48) b.y = height + 48;
        else if (b.y > height + 48) b.y = -48;
      }
      const breatheB = 0.5 + 0.5 * Math.sin(tSec * b.pulseSpeed + b.phase);
      const rB = b.baseR * (0.86 + breatheB * 0.30);
      const rgbB = paletteColors[b.colorKey] || paletteColors.accent;
      const gB = ctx.createRadialGradient(b.x, b.y, 1, b.x, b.y, rB);
      const coreAlpha = (isDark ? 0.11 : 0.072) * (0.65 + breatheB * 0.50);
      gB.addColorStop(0, rgbaStr(rgbB, coreAlpha));
      gB.addColorStop(0.55, rgbaStr(rgbB, coreAlpha * 0.36));
      gB.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = gB;
      ctx.beginPath();
      ctx.arc(b.x, b.y, rB, 0, Math.PI * 2);
      ctx.fill();
    }

    // 2. 8横 + 2纵横穿全屏丝线演化（0.80× 零跳变高弹拨弦 + 渐进非线性真丝恢复弹簧）
    const sampledRibbons = [];
    const gain = SILK_GAIN;
    const influenceR = 238 + gain * 22;
    const radialAmp = 540 * gain;
    const wakeAmp = 2.65 * gain;
    const baseSpring = 10.2;
    const stringTension = 78.0;
    const velDamp = Math.exp(-5.15 * dt);
    const hoverLerp = 1 - Math.exp(-7.6 * dt);
    const maxDisp = 82 + gain * 22;

    for (let sIdx = 0; sIdx < strands.length; sIdx++) {
      const st = strands[sIdx];
      const rgb1 = paletteColors[st.colorKey] || paletteColors.accent;
      const rgb2 = paletteColors[st.secondaryKey] || paletteColors.carbon;
      const nodes = st.nodes;
      const nLen = nodes.length;

      for (let k0 = 0; k0 < nLen; k0++) {
        prevOxBuf[k0] = nodes[k0].ox;
        prevOyBuf[k0] = nodes[k0].oy;
      }

      const pts = [];
      let maxKernel = 0;
      let peakIdx = 0;
      const breatheScale = 0.86 + 0.22 * Math.sin(tSec * 0.55 + st.phase);
      const localStiff = baseSpring * (st.stiffScale || 1.0);
      const localWake = wakeAmp * (st.wakeScale || 1.0);

      for (let k = 0; k < nLen; k++) {
        const u = k / (nLen - 1);
        const base = evalCrossScreenStrandRest(st, u, tSec, width, height, motionScale, breatheScale);
        const nd = nodes[k];

        if (!staticOnly) {
          let fx = 0;
          let fy = 0;

          if (pointer.presence > 0.002) {
            const dx = base.x - pointer.x;
            const dy = base.y - pointer.y;
            const r2 = dx * dx + dy * dy;
            if (r2 < influenceR * influenceR) {
              const r = Math.sqrt(r2);
              const uR = r / influenceR;
              const om = 1 - uR;
              const w = om * om * om * (3 * uR + 1);
              const effW = w * pointer.presence;
              if (effW > maxKernel) {
                maxKernel = effW;
                peakIdx = k;
              }

              const invSoft = 1 / Math.sqrt(r2 + 40 * 40);
              const radFx = dx * invSoft * radialAmp;
              const radFy = dy * invSoft * radialAmp;

              const vDotN = pointer.vx * base.nx + pointer.vy * base.ny;
              const vDotT = pointer.vx * base.tx + pointer.vy * base.ty;
              const pluckFx = pointer.vx * localWake + base.nx * vDotN * localWake * 0.62;
              const pluckFy = pointer.vy * localWake + base.ny * vDotN * localWake * 0.62;

              const breezeWave = Math.sin(u * 20 - tSec * 9.5 + st.phase) * vDotT * 1.15 * (gain * 0.5);
              const brzFx = base.nx * breezeWave;
              const brzFy = base.ny * breezeWave;

              fx += (radFx + pluckFx + brzFx) * effW * motionScale;
              fy += (radFy + pluckFy + brzFy) * effW * motionScale;
            }
          }

          for (let cwIdx = 0; cwIdx < clickWaves.length; cwIdx++) {
            const cWave = clickWaves[cwIdx];
            const cdx = base.x + prevOxBuf[k] - cWave.x;
            const cdy = base.y + prevOyBuf[k] - cWave.y;
            const cd = Math.hypot(cdx, cdy);
            const band = Math.abs(cd - cWave.r);
            if (band < 72) {
              const env = Math.pow(1 - band / 72, 2) * cWave.alpha * cWave.strength;
              const invCd = 1 / Math.sqrt(cd * cd + 34 * 34);
              const rippleForce = Math.sin((cd - cWave.r) * 0.09) * 680 * env;
              fx += cdx * invCd * rippleForce;
              fy += cdy * invCd * rippleForce;
            }
          }

          const prevLen2 = prevOxBuf[k] * prevOxBuf[k] + prevOyBuf[k] * prevOyBuf[k];
          const nonlinStiff = localStiff * (1 + prevLen2 / (maxDisp * maxDisp));
          const lapX =
            k > 0 && k < nLen - 1
              ? 0.5 * (prevOxBuf[k - 1] + prevOxBuf[k + 1]) - prevOxBuf[k]
              : -prevOxBuf[k] * 0.65;
          const lapY =
            k > 0 && k < nLen - 1
              ? 0.5 * (prevOyBuf[k - 1] + prevOyBuf[k + 1]) - prevOyBuf[k]
              : -prevOyBuf[k] * 0.65;

          fx += -nonlinStiff * prevOxBuf[k] + stringTension * lapX;
          fy += -nonlinStiff * prevOyBuf[k] + stringTension * lapY;

          nd.vx = (nd.vx + fx * dt) * velDamp;
          nd.vy = (nd.vy + fy * dt) * velDamp;
          nd.ox += nd.vx * dt;
          nd.oy += nd.vy * dt;

          const offLen = Math.hypot(nd.ox, nd.oy);
          const hardCap = maxDisp * 1.45;
          if (offLen > hardCap) {
            const scaleCap = hardCap / offLen;
            nd.ox *= scaleCap;
            nd.oy *= scaleCap;
            nd.vx *= 0.75;
            nd.vy *= 0.75;
          }
        }

        pts.push({ x: base.x + nd.ox, y: base.y + nd.oy });
      }

      sampledRibbons.push(pts);
      st.smoothHover += (maxKernel - st.smoothHover) * hoverLerp;

      const hoverBoost = st.smoothHover * (isDark ? 0.32 : 0.22);
      const firstPt = pts[0];
      const lastPt = pts[pts.length - 1];
      const lineGrad = ctx.createLinearGradient(firstPt.x, firstPt.y, lastPt.x, lastPt.y);
      lineGrad.addColorStop(0, rgbaStr(rgb1, 0.03));
      lineGrad.addColorStop(0.14, rgbaStr(rgb1, st.alpha * alphaBoost + hoverBoost * 0.65));
      lineGrad.addColorStop(0.50, rgbaStr(paletteColors.accent, st.alpha * 1.18 * alphaBoost + hoverBoost));
      lineGrad.addColorStop(0.86, rgbaStr(rgb2, st.alpha * alphaBoost + hoverBoost * 0.65));
      lineGrad.addColorStop(1, rgbaStr(rgb2, 0.03));

      ctx.beginPath();
      ctx.moveTo(firstPt.x, firstPt.y);
      for (let qi = 1; qi < pts.length - 1; qi++) {
        const xc = (pts[qi].x + pts[qi + 1].x) * 0.5;
        const yc = (pts[qi].y + pts[qi + 1].y) * 0.5;
        ctx.quadraticCurveTo(pts[qi].x, pts[qi].y, xc, yc);
      }
      ctx.lineTo(lastPt.x, lastPt.y);

      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      if (!isCalm) {
        ctx.strokeStyle = rgbaStr(rgb1, (st.alpha * 0.24 + hoverBoost * 0.34) * alphaBoost);
        ctx.lineWidth = st.width * 3.3 + st.smoothHover * 1.25;
        ctx.stroke();
      }
      ctx.strokeStyle = lineGrad;
      ctx.lineWidth = st.width + st.smoothHover * 0.52;
      ctx.stroke();

      if (!isCalm && st.smoothHover > 0.08) {
        const segStart = Math.max(0, peakIdx - 7);
        const segEnd = Math.min(pts.length - 1, peakIdx + 7);
        if (segEnd - segStart >= 2) {
          ctx.beginPath();
          ctx.moveTo(pts[segStart].x, pts[segStart].y);
          for (let si = segStart + 1; si < segEnd; si++) {
            const sxc = (pts[si].x + pts[si + 1].x) * 0.5;
            const syc = (pts[si].y + pts[si + 1].y) * 0.5;
            ctx.quadraticCurveTo(pts[si].x, pts[si].y, sxc, syc);
          }
          ctx.strokeStyle = rgbaStr(
            isDark ? [232, 228, 255] : paletteColors.accent,
            st.smoothHover * (isDark ? 0.38 : 0.26)
          );
          ctx.lineWidth = st.width + 0.55;
          ctx.stroke();
        }
      }
    }

    // 2B. 沿丝线巡游的流光脉冲微珠
    if (!staticOnly) {
      const beadLimit = isCalm ? Math.ceil(photonBeads.length * 0.5) : photonBeads.length;
      for (let pbIdx = 0; pbIdx < beadLimit; pbIdx++) {
        const bead = photonBeads[pbIdx];
        const poly = sampledRibbons[bead.strandIdx];
        if (!poly || poly.length < 2) continue;
        const rawU = (tSec * bead.speed * motionScale + bead.offset) % 1;
        const uBead = rawU < 0 ? rawU + 1 : rawU;
        const ptB = samplePolylineAt(poly, uBead);
        const edgeFade = Math.sin(uBead * Math.PI);
        const rgbBead = paletteColors[bead.colorKey] || paletteColors.accent;

        const haloR = bead.radius * 3.9;
        const hGrad = ctx.createRadialGradient(ptB.x, ptB.y, 0.4, ptB.x, ptB.y, haloR);
        hGrad.addColorStop(0, rgbaStr(rgbBead, (isDark ? 0.46 : 0.34) * edgeFade));
        hGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
        ctx.fillStyle = hGrad;
        ctx.beginPath();
        ctx.arc(ptB.x, ptB.y, haloR, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.arc(ptB.x, ptB.y, bead.radius, 0, Math.PI * 2);
        ctx.fillStyle = rgbaStr(isDark ? [245, 247, 255] : rgbBead, (isDark ? 0.80 : 0.65) * edgeFade);
        ctx.fill();
      }
    }

    // 3. 138 颗全 18 种镂空几何漂浮物演化 + 298px 等稳态加速磁吸旋涡与 258px 放射蛛网连线
    // 时间尺度等比加速（约 1.85×）：保持与原版完全一致的径向/切向力比（0.44 : 0.92）与阻尼平衡，仅加快趋近过程，绝不向心坍缩成团
    const activeCount = isCalm ? Math.floor(PARTICLE_COUNT * 0.58) : PARTICLE_COUNT;
    const proxMaxR = Math.max(220, SPIDER_RADIUS * 1.24);

    for (let i = 0; i < activeCount; i++) {
      const p = particles[i];
      if (!staticOnly) {
        const swirlX = Math.cos(tSec * 0.40 + p.driftSeed) * 0.12 * motionScale;
        const swirlY = Math.sin(tSec * 0.36 + p.driftSeed * 1.3) * 0.12 * motionScale;
        let inMagnetZone = false;
        let pdx = 0;
        let pdy = 0;
        let pDist = 0;
        if (pointer.presence > 0.01) {
          pdx = pointer.x - p.x;
          pdy = pointer.y - p.y;
          pDist = Math.hypot(pdx, pdy);
          if (pDist > 1 && pDist < MAGNET_RADIUS) {
            inMagnetZone = true;
          }
        }

        const pDamp = Math.pow(inMagnetZone ? 0.978 : 0.988, frameStep);
        p.vx = p.vx * pDamp + swirlX * 0.045 * frameStep;
        p.vy = p.vy * pDamp + swirlY * 0.045 * frameStep;

        if (inMagnetZone) {
          const pull = (1 - pDist / MAGNET_RADIUS) * 0.115 * motionScale * pointer.presence * frameStep;
          const radialSign = pDist < 50 ? -1.22 : 0.44;
          p.vx += (pdx / pDist) * pull * radialSign + (-pdy / pDist) * pull * 0.92;
          p.vy += (pdy / pDist) * pull * radialSign + (pdx / pDist) * pull * 0.92;
        }

        for (let jRep = i + 1; jRep < activeCount; jRep++) {
          const qRep = particles[jRep];
          const rdx = p.x - qRep.x;
          if (Math.abs(rdx) > 28) continue;
          const rdy = p.y - qRep.y;
          if (Math.abs(rdy) > 28) continue;
          const rd2 = rdx * rdx + rdy * rdy;
          if (rd2 > 0.1 && rd2 < 28 * 28) {
            const rd = Math.sqrt(rd2);
            const repPush = ((1 - rd / 28) * 0.024 * motionScale * frameStep) / rd;
            p.vx += rdx * repPush;
            p.vy += rdy * repPush;
            qRep.vx -= rdx * repPush;
            qRep.vy -= rdy * repPush;
          }
        }

        const speed = Math.hypot(p.vx, p.vy);
        const maxSpeed = inMagnetZone ? 2.55 : 1.75;
        if (speed > maxSpeed) {
          const nextSpd = inMagnetZone ? maxSpeed : Math.max(maxSpeed, speed * Math.pow(0.92, frameStep));
          p.vx = (p.vx / speed) * nextSpd;
          p.vy = (p.vy / speed) * nextSpd;
        }

        const prevX = p.x;
        const prevY = p.y;
        p.x += p.vx * frameStep;
        p.y += p.vy * frameStep;
        let wrapped = false;
        if (p.x < -24) {
          p.x = width + 24;
          wrapped = true;
        } else if (p.x > width + 24) {
          p.x = -24;
          wrapped = true;
        }
        if (p.y < -24) {
          p.y = height + 24;
          wrapped = true;
        } else if (p.y > height + 24) {
          p.y = -24;
          wrapped = true;
        }

        if (p.shape === "comet") {
          if (wrapped || Math.hypot(p.x - prevX, p.y - prevY) > 42) {
            p.trail.length = 0;
          } else {
            p.trail.push({ x: p.x, y: p.y });
            if (p.trail.length > 7) p.trail.shift();
          }
        }
      }

      const rgb = paletteColors[p.colorKey] || paletteColors.accent;
      const breathe = 0.5 + 0.5 * Math.sin(tSec * p.pulseSpeed * 1.65 + p.phase);
      let pointerProx = 0;

      // 252px 纤细高辨识度放射蛛网连线（保持 <1px 纤细笔触，提升明度层次）
      if (pointer.presence > 0.015) {
        const dPtr = Math.hypot(pointer.x - p.x, pointer.y - p.y);
        if (dPtr < proxMaxR) {
          pointerProx = (1 - dPtr / proxMaxR) * pointer.presence;
          if (dPtr < SPIDER_RADIUS) {
            const webFade = Math.pow(1 - dPtr / SPIDER_RADIUS, 0.82) * pointer.presence;
            const calmScale = isCalm ? 0.48 : 1;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(pointer.x, pointer.y);
            ctx.strokeStyle = rgbaStr(rgb, webFade * (isDark ? 0.44 : 0.34) * calmScale);
            ctx.lineWidth = 0.95;
            ctx.stroke();
          }
        }
      }

      // 132px 近邻星座蛛网连线（纤细 0.90px 丝线，非线性柔和衰减，清晰而绝不粗重）
      const calmLinkScale = isCalm ? 0.52 : 1;
      for (let j = i + 1; j < activeCount; j++) {
        const q = particles[j];
        const ldx = p.x - q.x;
        if (Math.abs(ldx) > CONSTELLATION_RADIUS) continue;
        const ldy = p.y - q.y;
        if (Math.abs(ldy) > CONSTELLATION_RADIUS) continue;
        const distPQ = Math.hypot(ldx, ldy);
        if (distPQ < CONSTELLATION_RADIUS) {
          const falloff = Math.pow(1 - distPQ / CONSTELLATION_RADIUS, 0.78);
          const linkAlpha =
            falloff * (isDark ? 0.275 : 0.195) * calmLinkScale * (1 + pointerProx * 1.65);
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(q.x, q.y);
          ctx.strokeStyle = rgbaStr(rgb, Math.min(0.62, linkAlpha));
          ctx.lineWidth = 0.90;
          ctx.stroke();
        }
      }

      const radius = p.baseR * (0.84 + breathe * 0.40 + pointerProx * 0.52);
      const alpha = (0.21 + breathe * 0.36 + pointerProx * 0.38) * alphaBoost;
      const rotNow = tSec * p.rotSpeed * motionScale + p.phase;

      drawHollowFloaterSpecies(ctx, p, radius, rgb, alpha, breathe, rotNow, isCalm);
    }

    // 3.5 鼠标掠影星尘微泡
    for (let mIdx = trailMotes.length - 1; mIdx >= 0; mIdx--) {
      const m = trailMotes[mIdx];
      m.x += m.vx * frameStep;
      m.y += m.vy * frameStep;
      m.vx *= Math.pow(0.96, frameStep);
      m.vy *= Math.pow(0.97, frameStep);
      m.rot += 0.035 * frameStep;
      m.life -= m.decay * frameStep;
      if (m.life <= 0.02) {
        trailMotes.splice(mIdx, 1);
        continue;
      }
      const rgb = paletteColors[m.colorKey] || paletteColors.accent;
      const a = m.life * (isDark ? 0.52 : 0.38);
      if (m.kind === "star") {
        drawCurvedFourStar(ctx, m.x, m.y, m.r * 1.68 * (0.5 + m.life * 0.5), 0.22, m.rot);
        ctx.strokeStyle = rgbaStr(rgb, a);
        ctx.lineWidth = 0.96;
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(m.x, m.y, m.r * (1.25 - m.life * 0.32), 0, Math.PI * 2);
        ctx.strokeStyle = rgbaStr(rgb, a * 0.88);
        ctx.lineWidth = 0.96;
        ctx.stroke();
      }
    }

    // 4. 6 种随机多态点击梦幻绽放特效
    for (let k = clickBursts.length - 1; k >= 0; k--) {
      const b = clickBursts[k];
      b.age += dt;
      const u = b.age / b.duration;
      if (u >= 1) {
        clickBursts.splice(k, 1);
        continue;
      }

      const easeOut = 1 - Math.pow(1 - u, 3);
      const fade = Math.pow(1 - u, 1.55) * (isDark ? 0.86 : 0.70);
      const rgb1 = paletteColors[b.primaryKey] || paletteColors.accent;
      const rgb2 = paletteColors[b.secondaryKey] || paletteColors.carbon;
      const rgb3 = paletteColors[b.tertiaryKey] || paletteColors.astra;

      if (u < 0.55) {
        const flashAlpha = (1 - u / 0.55) * (isDark ? 0.20 : 0.12);
        const fR = (26 + easeOut * 58) * b.scale;
        const fGrad = ctx.createRadialGradient(b.x, b.y, 1, b.x, b.y, fR);
        fGrad.addColorStop(0, rgbaStr(rgb1, flashAlpha));
        fGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
        ctx.fillStyle = fGrad;
        ctx.beginPath();
        ctx.arc(b.x, b.y, fR, 0, Math.PI * 2);
        ctx.fill();
      }

      if (b.kind === "nova") {
        const starR = (13 + easeOut * 48) * b.scale * (1 - u * 0.25);
        drawCurvedFourStar(ctx, b.x, b.y, starR, 0.18, b.rot0 + easeOut * 0.55);
        ctx.strokeStyle = rgbaStr(rgb1, fade * 0.92);
        ctx.lineWidth = 1.4;
        ctx.stroke();

        drawCurvedFourStar(ctx, b.x, b.y, starR * 0.68, 0.20, b.rot0 + Math.PI * 0.25 - easeOut * 0.45);
        ctx.strokeStyle = rgbaStr(rgb2, fade * 0.78);
        ctx.lineWidth = 1.1;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(b.x, b.y, (11 + easeOut * 88) * b.scale, 0, Math.PI * 2);
        ctx.strokeStyle = rgbaStr(rgb3, fade * 0.44);
        ctx.lineWidth = 1.05;
        ctx.stroke();

        for (const sp of b.sparks) {
          const curAng = sp.ang + easeOut * sp.swirl * 0.45;
          const dist = easeOut * sp.spd;
          const prevDist = Math.max(0, dist - 13 * (1 - u * 0.5) * b.scale);
          const sx = b.x + Math.cos(curAng) * dist;
          const sy = b.y + Math.sin(curAng) * dist;
          const px = b.x + Math.cos(curAng - sp.swirl * 0.06) * prevDist;
          const py = b.y + Math.sin(curAng - sp.swirl * 0.06) * prevDist;
          const sRgb = paletteColors[sp.colorKey] || rgb1;

          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(sx, sy);
          ctx.strokeStyle = rgbaStr(sRgb, fade * 0.86);
          ctx.lineWidth = sp.r * 0.7;
          ctx.lineCap = "round";
          ctx.stroke();

          ctx.beginPath();
          ctx.arc(sx, sy, sp.r * (1 - u * 0.45), 0, Math.PI * 2);
          ctx.fillStyle = rgbaStr(sRgb, fade);
          ctx.fill();
        }
      } else if (b.kind === "rosette") {
        const layers = [
          { lobes: 3, rBase: 50, amp: 18, rot: b.rot0 + easeOut * 1.12, rgb: rgb1, lw: 1.4 },
          { lobes: 3, rBase: 37, amp: 14, rot: -b.rot0 - easeOut * 1.32, rgb: rgb2, lw: 1.15 },
          { lobes: 5, rBase: 63, amp: 13, rot: b.rot0 * 0.6 + easeOut * 0.82, rgb: rgb3, lw: 0.98 },
        ];
        for (const ly of layers) {
          const scaleNow = (0.18 + easeOut * 0.90) * b.scale;
          const steps = 60;
          ctx.beginPath();
          for (let s = 0; s <= steps; s++) {
            const theta = (s / steps) * Math.PI * 2;
            const r = (ly.rBase + ly.amp * Math.cos(ly.lobes * theta)) * scaleNow;
            const phi = (ly.lobes === 3 ? 2 * theta : theta) + ly.rot;
            const px = b.x + Math.cos(phi) * r;
            const py = b.y + Math.sin(phi) * r;
            if (s === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          }
          ctx.closePath();
          ctx.strokeStyle = rgbaStr(ly.rgb, fade * 0.84);
          ctx.lineWidth = ly.lw;
          ctx.stroke();
        }
        for (const sp of b.sparks) {
          const curAng = sp.ang + easeOut * 0.62;
          const d = sp.dist * easeOut;
          const sx = b.x + Math.cos(curAng) * d;
          const sy = b.y + Math.sin(curAng) * d;
          const sRgb = paletteColors[sp.colorKey] || rgb1;
          drawCurvedFourStar(ctx, sx, sy, sp.r * 1.65 * (1 - u * 0.35), 0.22, curAng);
          ctx.strokeStyle = rgbaStr(sRgb, fade * 0.88);
          ctx.lineWidth = 0.98;
          ctx.stroke();
        }
      } else if (b.kind === "orbit") {
        const rx = (16 + easeOut * 86) * b.scale;
        const ry = rx * 0.38;

        ctx.save();
        ctx.translate(b.x, b.y);
        ctx.rotate(b.tiltA + easeOut * 0.35);
        ctx.beginPath();
        ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
        ctx.strokeStyle = rgbaStr(rgb1, fade * 0.88);
        ctx.lineWidth = 1.3;
        ctx.stroke();
        ctx.restore();

        ctx.save();
        ctx.translate(b.x, b.y);
        ctx.rotate(b.tiltB - easeOut * 0.35);
        ctx.beginPath();
        ctx.ellipse(0, 0, rx * 0.88, ry * 0.92, 0, 0, Math.PI * 2);
        ctx.strokeStyle = rgbaStr(rgb2, fade * 0.82);
        ctx.lineWidth = 1.15;
        ctx.stroke();
        ctx.restore();

        ctx.beginPath();
        ctx.arc(b.x, b.y, (8 + easeOut * 24) * b.scale, 0, Math.PI * 2);
        ctx.strokeStyle = rgbaStr(rgb3, fade * 0.62);
        ctx.lineWidth = 1.05;
        ctx.stroke();

        for (const sp of b.sparks) {
          const isA = sp.ringIdx === 0;
          const tilt = isA ? b.tiltA + easeOut * 0.35 : b.tiltB - easeOut * 0.35;
          const aRx = isA ? rx : rx * 0.88;
          const aRy = isA ? ry : ry * 0.92;
          const th = sp.phase0 + b.age * sp.omega;
          const lx = Math.cos(th) * aRx;
          const ly = Math.sin(th) * aRy;
          const gx = b.x + lx * Math.cos(tilt) - ly * Math.sin(tilt);
          const gy = b.y + lx * Math.sin(tilt) + ly * Math.cos(tilt);
          const sRgb = paletteColors[sp.colorKey] || rgb1;

          ctx.beginPath();
          ctx.arc(gx, gy, sp.r * (1.08 - u * 0.35), 0, Math.PI * 2);
          ctx.fillStyle = rgbaStr(sRgb, fade * 1.02);
          ctx.fill();
        }
      } else if (b.kind === "prism") {
        ctx.beginPath();
        ctx.arc(b.x, b.y, (10 + easeOut * 54) * b.scale, 0, Math.PI * 2);
        ctx.strokeStyle = rgbaStr(rgb1, fade * 0.40);
        ctx.lineWidth = 0.98;
        ctx.stroke();

        for (const sp of b.sparks) {
          const px = b.x + sp.dx * easeOut;
          const py = b.y + sp.dy * easeOut + sp.floatY * u * u;
          const sRgb = paletteColors[sp.colorKey] || rgb1;
          const rNow = sp.r * (1.06 - u * 0.42);
          drawRegularPolygon(ctx, px, py, rNow, sp.sides, sp.rot0 + b.age * sp.rotSpd);
          ctx.strokeStyle = rgbaStr(sRgb, fade * 0.90);
          ctx.lineWidth = 1.2;
          ctx.stroke();

          ctx.beginPath();
          ctx.arc(px, py, 1.1, 0, Math.PI * 2);
          ctx.fillStyle = rgbaStr(sRgb, fade * 0.75);
          ctx.fill();
        }
      } else if (b.kind === "harmonic") {
        const maxRadius = 124 * b.scale;
        for (let rIdx = 0; rIdx < 4; rIdx++) {
          const delay = rIdx * 0.11;
          if (u < delay) continue;
          const ru = Math.min(1, (u - delay) / (1 - delay));
          const rEase = 1 - Math.pow(1 - ru, 2.6);
          const rad = 8 + rEase * maxRadius * (1 - rIdx * 0.14);
          const rFade = Math.pow(1 - ru, 1.5) * (isDark ? 0.80 : 0.64);
          const ringRgb = rIdx % 2 === 0 ? rgb1 : rIdx === 1 ? rgb2 : rgb3;

          ctx.save();
          if (rIdx % 2 === 1) {
            ctx.setLineDash([5, 6]);
          }
          ctx.beginPath();
          ctx.arc(b.x, b.y, rad, 0, Math.PI * 2);
          ctx.strokeStyle = rgbaStr(ringRgb, rFade);
          ctx.lineWidth = rIdx === 0 ? 1.4 : 1.05;
          ctx.stroke();
          ctx.restore();
        }

        const dialR = (16 + easeOut * 80) * b.scale;
        for (let t = 0; t < b.ticks; t++) {
          const ang = b.rot0 + (t / b.ticks) * Math.PI * 2 + easeOut * 0.28;
          const inner = dialR - (t % 2 === 0 ? 5.0 : 2.8);
          const outer = dialR + (t % 2 === 0 ? 4.2 : 1.8);
          ctx.beginPath();
          ctx.moveTo(b.x + Math.cos(ang) * inner, b.y + Math.sin(ang) * inner);
          ctx.lineTo(b.x + Math.cos(ang) * outer, b.y + Math.sin(ang) * outer);
          ctx.strokeStyle = rgbaStr(rgb2, fade * (t % 2 === 0 ? 0.68 : 0.38));
          ctx.lineWidth = 0.95;
          ctx.stroke();
        }
      } else if (b.kind === "constellation") {
        const nodes = b.sparks.map((sp) => {
          const rot = easeOut * sp.swirl;
          const cosR = Math.cos(rot);
          const sinR = Math.sin(rot);
          const rx = sp.dx * cosR - sp.dy * sinR;
          const ry = sp.dx * sinR + sp.dy * cosR;
          return {
            x: b.x + rx * easeOut,
            y: b.y + ry * easeOut,
            r: sp.r,
            isStar: sp.isStar,
            rgb: paletteColors[sp.colorKey] || rgb1,
          };
        });

        const maxLink = 64 * b.scale;
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const d = Math.hypot(nodes[i].x - nodes[j].x, nodes[i].y - nodes[j].y);
            if (d < maxLink) {
              const lAlpha = (1 - d / maxLink) * fade * 0.68;
              ctx.beginPath();
              ctx.moveTo(nodes[i].x, nodes[i].y);
              ctx.lineTo(nodes[j].x, nodes[j].y);
              ctx.strokeStyle = rgbaStr(nodes[i].rgb, lAlpha);
              ctx.lineWidth = 0.9;
              ctx.stroke();
            }
          }
        }

        for (const nd of nodes) {
          if (nd.isStar) {
            drawCurvedFourStar(ctx, nd.x, nd.y, nd.r * 2.0 * (1 - u * 0.3), 0.22, b.rot0 + easeOut);
            ctx.strokeStyle = rgbaStr(nd.rgb, fade * 0.92);
            ctx.lineWidth = 1.05;
            ctx.stroke();
          } else {
            ctx.beginPath();
            ctx.arc(nd.x, nd.y, nd.r * (1.12 - u * 0.35), 0, Math.PI * 2);
            ctx.strokeStyle = rgbaStr(nd.rgb, fade * 0.92);
            ctx.lineWidth = 1.2;
            ctx.stroke();
          }
        }
      }
    }
  }

  let rafId = 0;
  const tick = (nowMs) => {
    rafId = 0;
    if (document.hidden || reducedMotionMql.matches) {
      return;
    }
    renderKineticFrame(nowMs * 0.001, false);
    rafId = requestAnimationFrame(tick);
  };

  function ensureLoopRunning() {
    if (reducedMotionMql.matches) {
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = 0;
      }
      renderKineticFrame(performance.now() * 0.001, true);
      return;
    }
    if (!document.hidden && !rafId) {
      lastFrameSec = performance.now() * 0.001;
      rafId = requestAnimationFrame(tick);
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden && rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    } else if (!document.hidden) {
      ensureLoopRunning();
    }
  });

  if (typeof reducedMotionMql.addEventListener === "function") {
    reducedMotionMql.addEventListener("change", ensureLoopRunning);
  }

  ensureLoopRunning();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initV4Enhancements);
} else {
  initV4Enhancements();
}
