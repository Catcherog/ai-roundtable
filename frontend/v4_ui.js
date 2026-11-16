/**
 * AI圆桌 v4 — 多模态文件/图片附件管线、8席空心线性矢量徽标水合、悬浮胶囊输入舱与配置芯片控制器
 * 视觉统一准则：全套 1.65px 圆头空心线性 SVG（以线代面），零 Emoji / 裸符号混排，100% 兼容现有 DOM 契约。
 */

const SEAT_VECTOR_ICONS = {
  carbon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 3.5 20.5 8 12 12.5 3.5 8 12 3.5"></polygon><polyline points="3.5 12.8 12 17.2 20.5 12.8"></polyline><polyline points="5.5 17 12 20.5 18.5 17"></polyline></svg>`,
  grok: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20.8s7.2-3.6 7.2-9.2V5.4L12 2.8 4.8 5.4v6.2c0 5.6 7.2 9.2 7.2 9.2z"></path><circle cx="12" cy="11.4" r="2.5"></circle></svg>`,
  astra: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><polyline points="7.2 8.2 3.2 12 7.2 15.8"></polyline><polyline points="16.8 8.2 20.8 12 16.8 15.8"></polyline><line x1="13.6" y1="5.2" x2="10.4" y2="18.8"></line></svg>`,
  vega: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 3.2 18.2 11.8 12 20.8 5.8 11.8 12 3.2"></polygon><line x1="12" y1="3.2" x2="12" y2="10.2"></line><circle cx="12" cy="12" r="1.8"></circle></svg>`,
  titan: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polyline points="2.8 12 7.2 12 10 5 14 19 16.8 12 21.2 12"></polyline></svg>`,
  prism: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2.8 20.2 7.5 20.2 16.5 12 21.2 3.8 16.5 3.8 7.5 12 2.8"></polygon><polyline points="8.4 12.2 11 14.8 15.8 9.6"></polyline></svg>`,
  chair: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2.8 14.6 9.4 21.2 12 14.6 14.6 12 21.2 9.4 14.6 2.8 12 9.4 9.4 12 2.8"></polygon></svg>`,
  system: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.4"></circle><circle cx="12" cy="12" r="2.8"></circle></svg>`,
};

const LINEAR_UI_ICONS = {
  paperclip: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="13.5" height="13.5" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.2 11.2l-8.8 8.8a5.8 5.8 0 0 1-8.2-8.2l8.8-8.8a3.9 3.9 0 0 1 5.5 5.5l-8.8 8.8a1.95 1.95 0 0 1-2.76-2.76l8.1-8.1"></path></svg>`,
  close: `<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="6" y1="6" x2="18" y2="18"></line><line x1="18" y1="6" x2="6" y2="18"></line></svg>`,
  adopt: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12.5" height="12.5" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"></circle><polyline points="8.4 12.2 11 14.8 15.8 9.6"></polyline></svg>`,
  discuss: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12.5" height="12.5" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8A2.5 2.5 0 0 1 17.5 17H9l-4.2 3.2V17A2.5 2.5 0 0 1 4 14.5z"></path></svg>`,
  pin: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8.5 4h7l-1.2 6.2L17.5 13H6.5l3.2-2.8z"></path><line x1="12" y1="13" x2="12" y2="20"></line></svg>`,
  edit: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 19.5l1.4-4.8L15.2 5.4a1.8 1.8 0 0 1 2.5 2.5L8.4 17.2z"></path><line x1="4.5" y1="20.5" x2="19.5" y2="20.5"></line></svg>`,
  copy: `<svg class="v4-inline-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8.5" y="8.5" width="11" height="11" rx="2.2"></rect><path d="M5.5 15.5H5a2 2 0 0 1-2-2v-8.5a2 2 0 0 1 2-2h8.5a2 2 0 0 1 2 2v.5"></path></svg>`,
};

const MODEL_CHIPS_BY_DRIVER = {
  agy: [
    { value: "gemini-4-carbon", label: "Carbon" },
    { value: "gemini-4-argon", label: "Argon" },
    { value: "gemini-4-hydrogen", label: "Hydrogen" },
  ],
  grok: [
    { value: "grok-4.7", label: "Grok 4.7" },
  ],
  codex: [
    { value: "gpt-6-astra", label: "GPT-6 Astra" },
    { value: "gpt-6.1-sol", label: "GPT-6.1 Sol" },
  ],
  auto: [
    { value: "", label: "跟随驱动默认" },
    { value: "gemini-4-carbon", label: "Carbon" },
    { value: "gpt-6-astra", label: "Astra" },
    { value: "grok-4.7", label: "Grok 4.7" },
  ],
};

const MODE_SHORT_LABELS = {
  deep_deliberation: "深度研讨",
  adversarial_review: "正反辩证",
  divergent_convergent: "发散收敛",
  code_review: "代码审查",
  rapid_consensus: "快速合议",
};

const SEAT_CAPS = ["Carbon", "Grok", "Astra", "Vega", "Titan", "Prism"];

const v4State = {
  token: "",
  activeSessionId: "",
  pendingAttachments: [], // [{ id, name, kind, mime_type, size_human, width, height, line_count, previewUrl, uploading }]
  blobUrlCache: new Map(), // key: `${sid}:${attId}` -> objectURL
  msgAttachmentsById: new Map(), // msgId -> attachments[]
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

/* ==================== 1. 透明拦截增强 fetch：同步鉴权令牌、会话 ID 与附件自动挂载 ==================== */

const rawFetch = window.fetch.bind(window);

window.fetch = async function patchedRoundtableFetch(input, init = {}) {
  const urlStr = typeof input === "string" ? input : input?.url || "";
  const hdrs = init?.headers || {};
  const tok =
    hdrs["X-Roundtable-Token"] ||
    hdrs["x-roundtable-token"] ||
    (hdrs instanceof Headers ? hdrs.get("X-Roundtable-Token") : "");
  if (tok) {
    v4State.token = String(tok);
  }

  const sessStreamMatch = urlStr.match(/\/api\/sessions\/([^/?#]+)\/stream/);
  if (sessStreamMatch && sessStreamMatch[1]) {
    const nextSid = decodeURIComponent(sessStreamMatch[1]);
    if (v4State.activeSessionId && v4State.activeSessionId !== nextSid) {
      v4State.pendingAttachments = [];
      renderPendingAttachmentTray();
    }
    v4State.activeSessionId = nextSid;
    setTimeout(() => syncSessionMessageAttachments(nextSid), 260);
  }

  // 在发起研讨 / 插话 / 追问请求时，自动附加待发送附件 ID 列表
  const sendMatch = urlStr.match(/\/api\/sessions\/([^/?#]+)\/(start|interrupt|followup)$/);
  const readyPending = v4State.pendingAttachments.filter((a) => a.id && !a.uploading);
  let injectedAttsSnapshot = null;

  if (sendMatch && init?.method?.toUpperCase() === "POST" && readyPending.length > 0 && typeof init.body === "string") {
    try {
      const parsedBody = JSON.parse(init.body);
      parsedBody.attachment_ids = readyPending.map((a) => a.id);
      if (sendMatch[2] === "start" && !String(parsedBody.topic || "").trim()) {
        parsedBody.topic = `请结合上传的附件（${readyPending.map((a) => a.name).slice(0, 3).join("、")}）开展协同研讨并给出落地方案。`;
      } else if (sendMatch[2] !== "start" && !String(parsedBody.message || "").trim()) {
        parsedBody.message = `补充上传了参考附件（${readyPending.map((a) => a.name).slice(0, 3).join("、")}），请结合附件内容继续评估。`;
      }
      init = { ...init, body: JSON.stringify(parsedBody) };
      injectedAttsSnapshot = [...readyPending];
    } catch {
      // 保持原请求体
    }
  }

  const resp = await rawFetch(input, init);

  // 捕获 bootstrap 返回令牌或创建新会话 ID
  if (resp.ok && urlStr.includes("/api/auth/bootstrap")) {
    resp
      .clone()
      .json()
      .then((d) => {
        if (d?.token) v4State.token = String(d.token);
      })
      .catch(() => {});
  } else if (resp.ok && urlStr === "/api/status") {
    resp
      .clone()
      .json()
      .then((d) => {
        if (!v4State.activeSessionId && d?.default_session_id) {
          v4State.activeSessionId = String(d.default_session_id);
        }
      })
      .catch(() => {});
  } else if (resp.ok && injectedAttsSnapshot && sendMatch) {
    const sid = decodeURIComponent(sendMatch[1]);
    v4State.pendingAttachments = v4State.pendingAttachments.filter(
      (p) => !injectedAttsSnapshot.some((sent) => sent.id === p.id)
    );
    renderPendingAttachmentTray();
    setTimeout(() => syncSessionMessageAttachments(sid), 240);
  }

  return resp;
};

/* ==================== 2. 多模态文件与图片读取、上传与预览灯箱 ==================== */

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const res = String(reader.result || "");
      const comma = res.indexOf(",");
      resolve(comma >= 0 ? res.slice(comma + 1) : res);
    };
    reader.onerror = () => reject(new Error(`读取文件失败：${file.name}`));
    reader.readAsDataURL(file);
  });
}

async function fetchAttachmentBlobUrl(sessionId, attId, existingPreview = "") {
  if (existingPreview) return existingPreview;
  const cacheKey = `${sessionId}:${attId}`;
  if (v4State.blobUrlCache.has(cacheKey)) {
    return v4State.blobUrlCache.get(cacheKey);
  }
  if (!v4State.token || !sessionId || !attId) return "";
  try {
    const res = await rawFetch(`/api/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(attId)}/raw`, {
      method: "GET",
      headers: { "X-Roundtable-Token": v4State.token },
    });
    if (!res.ok) return "";
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    v4State.blobUrlCache.set(cacheKey, objUrl);
    return objUrl;
  } catch {
    return "";
  }
}

export async function handleSelectedFiles(fileList) {
  const files = Array.from(fileList || []).filter(Boolean);
  if (!files.length) return;
  const sid = v4State.activeSessionId;
  if (!sid) {
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
    const placeholder = {
      tempKey,
      id: "",
      name: file.name || `粘贴截图_${new Date().toTimeString().slice(0, 8).replace(/:/g, "")}.png`,
      kind: isImg ? "image" : "doc",
      mime_type: file.type || "application/octet-stream",
      size_human: file.size < 1024 ? `${file.size} B` : `${(file.size / 1024).toFixed(1)} KB`,
      width: 0,
      height: 0,
      line_count: 0,
      ext: (file.name.match(/\.[A-Za-z0-9]+$/) || [""])[0],
      previewUrl: localPreviewUrl,
      uploading: true,
    };
    v4State.pendingAttachments.push(placeholder);
    renderPendingAttachmentTray();

    try {
      const b64 = await readFileAsBase64(file);
      const res = await rawFetch(`/api/sessions/${encodeURIComponent(sid)}/attachments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(v4State.token ? { "X-Roundtable-Token": v4State.token } : {}),
        },
        body: JSON.stringify({
          filename: placeholder.name,
          mime_type: file.type || "",
          data_base64: b64,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data?.attachment?.id) {
        throw new Error(data.error || `上传失败 (${res.status})`);
      }
      const saved = data.attachment;
      if (localPreviewUrl) {
        v4State.blobUrlCache.set(`${sid}:${saved.id}`, localPreviewUrl);
      }
      const idx = v4State.pendingAttachments.findIndex((x) => x.tempKey === tempKey);
      if (idx >= 0) {
        // 去重同 ID 附件
        const dupIdx = v4State.pendingAttachments.findIndex((x, i) => i !== idx && x.id === saved.id);
        if (dupIdx >= 0) {
          v4State.pendingAttachments.splice(idx, 1);
        } else {
          v4State.pendingAttachments[idx] = {
            ...saved,
            previewUrl: localPreviewUrl,
            uploading: false,
          };
        }
      }
      renderPendingAttachmentTray();
      ensureSendableWithAttachmentOnly();
    } catch (err) {
      v4State.pendingAttachments = v4State.pendingAttachments.filter((x) => x.tempKey !== tempKey);
      renderPendingAttachmentTray();
      notifyToast(err.message || `上传附件 ${file.name} 失败`, "err");
    }
  }
}

function ensureSendableWithAttachmentOnly() {
  const inp = $id("topicInput");
  if (!inp) return;
  if (v4State.pendingAttachments.some((a) => a.id && !a.uploading) && !inp.placeholder.includes("可直接点击")) {
    inp.placeholder = "已就绪附件 · 可补充说明，或直接按 Enter / 点击右侧按钮开启多模态研讨";
  }
}

function renderPendingAttachmentTray() {
  const tray = $id("v4AttachmentTray");
  if (!tray) return;
  if (!v4State.pendingAttachments.length) {
    tray.classList.add("hidden");
    tray.innerHTML = "";
    return;
  }
  tray.classList.remove("hidden");
  tray.innerHTML = v4State.pendingAttachments
    .map((att, idx) => {
      const extLabel = String(att.ext || "").replace(".", "").toUpperCase().slice(0, 4) || (att.kind === "code" ? "CODE" : "FILE");
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
      const item = v4State.pendingAttachments[Number(imgEl.dataset.v4ZoomIdx)];
      if (item?.previewUrl) {
        openImageLightbox(item.previewUrl, `${item.name} (${item.width && item.height ? `${item.width}×${item.height} · ` : ""}${item.size_human || ""})`);
      }
    };
  });

  tray.querySelectorAll("[data-v4-rm-idx]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const idx = Number(btn.dataset.v4RmIdx);
      const removed = v4State.pendingAttachments[idx];
      v4State.pendingAttachments.splice(idx, 1);
      renderPendingAttachmentTray();
      if (removed?.id && v4State.activeSessionId && v4State.token) {
        rawFetch(`/api/sessions/${encodeURIComponent(v4State.activeSessionId)}/attachments/${encodeURIComponent(removed.id)}`, {
          method: "DELETE",
          headers: { "X-Roundtable-Token": v4State.token },
        }).catch(() => {});
      }
    };
  });
}

function openImageLightbox(src, caption = "") {
  const modal = $id("v4LightboxModal");
  const img = $id("v4LightboxImg");
  const cap = $id("v4LightboxCaption");
  if (!modal || !img) return;
  img.src = src;
  if (cap) cap.textContent = caption || "图片预览";
  modal.classList.remove("hidden");
}

function closeImageLightbox() {
  const modal = $id("v4LightboxModal");
  if (modal) modal.classList.add("hidden");
}

async function syncSessionMessageAttachments(sessionId) {
  if (!sessionId || !v4State.token) return;
  try {
    const res = await rawFetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: "GET",
      headers: { "X-Roundtable-Token": v4State.token },
    });
    if (!res.ok) return;
    const data = await res.json();
    const msgs = data?.session?.messages || [];
    for (const m of msgs) {
      if (m?.id && Array.isArray(m.attachments) && m.attachments.length > 0) {
        v4State.msgAttachmentsById.set(m.id, m.attachments);
      }
    }
    await decorateMessageAttachmentGalleries();
  } catch {
    // 忽略后台拉取异常
  }
}

async function decorateMessageAttachmentGalleries() {
  const sid = v4State.activeSessionId;
  for (const [msgId, atts] of v4State.msgAttachmentsById.entries()) {
    const card = document.getElementById(`msg-${msgId}`);
    if (!card || !Array.isArray(atts) || !atts.length) continue;
    let gallery = card.querySelector(".v4-msg-attachments");
    if (gallery && Number(gallery.dataset.attCount || "0") === atts.length) continue;
    if (!gallery) {
      gallery = document.createElement("div");
      gallery.className = "v4-msg-attachments";
      card.appendChild(gallery);
    }
    gallery.dataset.attCount = String(atts.length);

    const parts = [];
    for (const att of atts) {
      if (att.kind === "image") {
        const blobUrl = await fetchAttachmentBlobUrl(sid, att.id);
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
    gallery.innerHTML = parts.join("");
    gallery.querySelectorAll("[data-lightbox-src]").forEach((node) => {
      node.onclick = (e) => {
        e.stopPropagation();
        openImageLightbox(node.dataset.lightboxSrc, node.dataset.lightboxCap);
      };
    });
  }
}

/* ==================== 3. 8 席空心线性矢量徽标与白板操作微图标水合器 ==================== */

function hydrateVectorIcons() {
  // 1. 顶栏与设置弹窗席位徽章（注意 app.js syncDynamicRosterNames 会重置 textContent，水合器自动实时恢复 SVG）
  document.querySelectorAll("[data-seat-icon]").forEach((node) => {
    const key = node.dataset.seatIcon;
    const svg = SEAT_VECTOR_ICONS[key];
    if (svg && !node.querySelector("svg")) {
      node.innerHTML = svg;
    }
  });

  // 2. 消息流发言卡片迷你头像与右侧操作微图标
  document.querySelectorAll(".msg-card").forEach((card) => {
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
  });

  // 3. 右侧会议白板来源迷你徽章（将单汉字圆点升级为同源线性微缩 SVG）及操作按钮微图标
  document.querySelectorAll(".wb-seat-mini-badge").forEach((badge) => {
    const dot = badge.querySelector(".mini-seat-dot");
    if (!dot || dot.querySelector("svg")) return;
    for (const key of Object.keys(SEAT_VECTOR_ICONS)) {
      if (badge.classList.contains(`badge-seat-${key}`)) {
        dot.innerHTML = SEAT_VECTOR_ICONS[key];
        break;
      }
    }
  });

  document.querySelectorAll(".wb-pool-actions").forEach((bar) => {
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

  // 4. 侧栏历史删除、源码胶囊移除与任务勾选框统一水合为线性 SVG
  document.querySelectorAll(".session-del-btn, .chip-file-remove").forEach((btn) => {
    if (!btn.querySelector("svg")) {
      btn.innerHTML = LINEAR_UI_ICONS.close;
    }
  });
  document.querySelectorAll(".wb-task-check.checked").forEach((chk) => {
    if (!chk.querySelector("svg")) {
      chk.innerHTML = `<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="5 12.5 9.6 17 19 7.5"></polyline></svg>`;
    }
  });
}

/* ==================== 4. 配置中心「模型快选芯片」与「档位分段胶囊」双向同步 ==================== */

function renderSeatModelAndEffortChips(seatCap) {
  const drvSel = $id(`cfg${seatCap}Driver`);
  const modelInp = $id(`cfg${seatCap}Model`);
  const chipBar = $id(`v4ModelChips${seatCap}`);
  const discSel = $id(`cfg${seatCap}Effort`);
  const execSel = $id(`cfg${seatCap}ExecEffort`);
  const effortSeg = $id(`v4EffortSeg${seatCap}`);
  if (!drvSel || !modelInp || !chipBar || !discSel || !effortSeg) return;

  const drv = drvSel.value || "auto";
  const chips = MODEL_CHIPS_BY_DRIVER[drv] || MODEL_CHIPS_BY_DRIVER.auto;
  const curModel = modelInp.value.trim();
  const matchesPreset = chips.some((c) => c.value.toLowerCase() === curModel.toLowerCase());

  chipBar.innerHTML = chips
    .map((c) => {
      const isAct = c.value.toLowerCase() === curModel.toLowerCase() || (!curModel && c.value === chips[0].value);
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

  // 同步合法推理档位胶囊条，并默认将执行档位对齐讨论档位
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

function refreshAllModalSeatChips() {
  SEAT_CAPS.forEach((cap) => renderSeatModelAndEffortChips(cap));
}

/* ==================== 5. 输入舱策略胶囊摘要同步与纯附件直发支持 ==================== */

function syncComposerStrategySummary() {
  const txtEl = $id("v4StrategySummaryText");
  const autoDot = $id("v4AutoExecDot");
  if (!txtEl) return;

  const activeModeBtn = document.querySelector("#inlineModeSelect .mode-seg-pill.active");
  const modeKey = activeModeBtn?.dataset.collabOpt || "deep_deliberation";
  const modeLabel = MODE_SHORT_LABELS[modeKey] || "深度研讨";

  const ringCountTxt = ($id("ringSeatCountLabel")?.textContent || "3 席").replace("参会", "").trim();
  const summary = `${modeLabel} · ${ringCountTxt}`;
  if (txtEl.textContent !== summary) txtEl.textContent = summary;

  const autoOn = Boolean($id("composerAutoPreviewBtn")?.classList.contains("active"));
  autoDot?.classList.toggle("hidden", !autoOn);
}

function closeV4Popovers() {
  $id("v4AttachPopover")?.classList.add("hidden");
  $id("v4PlusAttachBtn")?.setAttribute("aria-expanded", "false");
  $id("v4ModePopover")?.classList.add("hidden");
  $id("v4ModeTriggerPill")?.setAttribute("aria-expanded", "false");
}

/* ==================== 6. 事件绑定与生命周期启动 ==================== */

function initV4Enhancements() {
  hydrateVectorIcons();
  syncComposerStrategySummary();

  // 监听 DOM 变化，实时水合新增发言卡/白板 SVG 图标、挂载消息附件画廊并刷新策略胶囊文案
  const obsTarget = document.body;
  let rafScheduled = false;
  const observer = new MutationObserver(() => {
    if (rafScheduled) return;
    rafScheduled = true;
    requestAnimationFrame(() => {
      rafScheduled = false;
      hydrateVectorIcons();
      syncComposerStrategySummary();
      decorateMessageAttachmentGalleries();
    });
  });
  observer.observe(obsTarget, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });

  // 1. Launchpad 展开/收起 4–6 席高阶预设
  const morePresetsBtn = $id("v4ToggleMorePresetsBtn");
  morePresetsBtn?.addEventListener("click", () => {
    const extras = document.querySelectorAll(".v4-extra-scenario");
    const isNowOpen = extras[0]?.classList.contains("hidden");
    extras.forEach((card) => card.classList.toggle("hidden", !isNowOpen));
    morePresetsBtn.setAttribute("aria-expanded", isNowOpen ? "true" : "false");
    const span = morePresetsBtn.querySelector("span");
    if (span) span.textContent = isNowOpen ? "收起 4–6 席高阶阵容" : "展开 4–6 席高阶阵容";
  });

  // 2. 结构化纯文本槽位胶囊（零系统文件弹窗副作用，点击仅向输入舱追加结构化维度引导）
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

  // 3. [+] 菜单与快捷附件按钮
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

  // 4. 剪贴板 ⌘V 直接粘贴截图或文件
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

  // 5. 全窗口拖拽添加图片与文件
  const dropOverlay = $id("v4DropOverlay");
  window.addEventListener("dragenter", (e) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    v4State.dragDepth += 1;
    dropOverlay?.classList.remove("hidden");
  });
  window.addEventListener("dragover", (e) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  });
  window.addEventListener("dragleave", (e) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    v4State.dragDepth = Math.max(0, v4State.dragDepth - 1);
    if (v4State.dragDepth === 0) {
      dropOverlay?.classList.add("hidden");
    }
  });
  window.addEventListener("drop", async (e) => {
    if (!e.dataTransfer?.files?.length) return;
    e.preventDefault();
    v4State.dragDepth = 0;
    dropOverlay?.classList.add("hidden");
    await handleSelectedFiles(e.dataTransfer.files);
    $id("topicInput")?.focus();
  });

  // 6. 纯附件免填字一键发送支持（当输入框为空但已挂有就绪附件时自动填入语义引导词）
  const prefillIfAttachmentOnly = () => {
    const inp = $id("topicInput");
    const ready = v4State.pendingAttachments.filter((a) => a.id && !a.uploading);
    if (inp && !inp.value.trim() && ready.length > 0) {
      inp.value = `请结合所附文件/截图（${ready.map((a) => a.name).slice(0, 3).join("、")}）进行协同分析并给出具体方案。`;
      inp.dispatchEvent(new Event("input", { bubbles: true }));
    }
  };
  $id("primaryActionBtn")?.addEventListener("click", prefillIfAttachmentOnly, true);
  $id("topicInput")?.addEventListener(
    "keydown",
    (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
        prefillIfAttachmentOnly();
      }
    },
    true
  );

  // 7. 策略与阵容速调胶囊浮层
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

  // 8. 配置中心：三分导航兼容映射 + 模型芯片联动
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

  // 9. 图片预览灯箱关闭与全局快捷键（⌘U 添加附件 / Esc 关闭浮层与灯箱）
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

  // 扩展原生菜单钩子 window.__roundtableMenu('attachFiles')
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
