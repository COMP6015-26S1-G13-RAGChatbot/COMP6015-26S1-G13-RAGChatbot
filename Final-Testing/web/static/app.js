(function () {
  "use strict";

  // ============================================================
  // CONFIG
  // ============================================================

  var STORE_KEY = "smcs-conversations";
  var THEME_KEY = "smcs-theme";
  var MAX_CONVERSATIONS = 30;

  var SUGGESTIONS = [
    { tag: "Voting", text: "Is proxy voting allowed at an SMCS Board of Governors meeting?" },
    { tag: "Quorum", text: "What constitutes a quorum for the SMCS Board of Governors?" },
    { tag: "Board", text: "How many voting members can the SMCS Board of Governors have at most?" },
    { tag: "Terms", text: "What is the term of office for an SMCS Member-at-Large on the Board of Governors?" },
    { tag: "Committees", text: "What is the minimum number of IEEE SMC Society members required to be listed as founding members of a new technical committee?" },
    { tag: "Meetings", text: "How often must the SMCS Executive Committee meet?" }
  ];

  var STAGES = [
    "Searching the knowledge base…",
    "Ranking authoritative sources…",
    "Checking for conflicting rules…",
    "Generating a grounded answer…"
  ];

  var ICONS = {
    bot: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3 4 6.5v5c0 4.6 3.3 8.4 8 9.5 4.7-1.1 8-4.9 8-9.5v-5L12 3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="m8.5 12 2.5 2.5 4.5-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    file: '<svg viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z"/><path d="M14 3v5h5"/></svg>',
    book: '<svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14Z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/></svg>',
    external: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
    chevron: '<svg class="chev" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>',
    warn: '<svg viewBox="0 0 24 24"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="m5 12 5 5 9-10"/></svg>',
    copy: '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>',
    terminal: '<svg viewBox="0 0 24 24"><path d="m5 8 4 4-4 4M12 16h7"/></svg>',
    retry: '<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
    info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5h1"/></svg>',
    alert: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>',
    trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>',
    clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
  };

  // ============================================================
  // ELEMENTS
  // ============================================================

  var $ = function (id) { return document.getElementById(id); };

  var els = {
    sidebar: $("sidebar"),
    scrim: $("scrim"),
    menuBtn: $("menuBtn"),
    sidebarClose: $("sidebarClose"),
    newChat: $("newChat"),
    history: $("history"),
    docList: $("docList"),
    status: $("status"),
    themeToggle: $("themeToggle"),
    title: $("chatTitle"),
    thread: $("thread"),
    welcome: $("welcome"),
    suggestions: $("suggestions"),
    composer: $("composer"),
    input: $("input"),
    send: $("send"),
    toast: $("toast")
  };

  // ============================================================
  // STATE
  // ============================================================

  var conversations = loadConversations();
  var current = null;
  var busy = false;

  function loadConversations() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function saveConversations() {
    try {
      localStorage.setItem(
        STORE_KEY,
        JSON.stringify(conversations.slice(0, MAX_CONVERSATIONS))
      );
    } catch (e) { /* storage unavailable: keep in memory only */ }
  }

  function uid() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  // ============================================================
  // HELPERS
  // ============================================================

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function inline(text) {
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  // Small, safe Markdown subset: paragraphs, bullet and numbered lists,
  // bold and inline code.
  function renderMarkdown(text) {
    var lines = String(text || "").replace(/\r/g, "").split("\n");
    var html = [];
    var list = null;
    var para = [];

    function flushPara() {
      if (para.length) {
        html.push("<p>" + inline(para.join(" ")) + "</p>");
        para = [];
      }
    }

    function flushList() {
      if (list) {
        html.push("<" + list.tag + ">" + list.items.join("") + "</" + list.tag + ">");
        list = null;
      }
    }

    lines.forEach(function (line) {
      var trimmed = line.trim();
      var bullet = trimmed.match(/^[-*•]\s+(.*)$/);
      var numbered = trimmed.match(/^\d+[.)]\s+(.*)$/);

      if (bullet || numbered) {
        flushPara();
        var tag = bullet ? "ul" : "ol";
        if (!list || list.tag !== tag) {
          flushList();
          list = { tag: tag, items: [] };
        }
        list.items.push("<li>" + inline((bullet || numbered)[1]) + "</li>");
      } else if (!trimmed) {
        flushPara();
        flushList();
      } else {
        flushList();
        para.push(trimmed);
      }
    });

    flushPara();
    flushList();
    return html.join("");
  }

  function categoryLabel(category) {
    var c = String(category || "").toLowerCase();
    return c ? c.charAt(0).toUpperCase() + c.slice(1) : "Source";
  }

  function prettyName(source) {
    return String(source || "Unknown").replace(/\.pdf$/i, "").replace(/[_-]+/g, " ");
  }

  function humanTopic(topic) {
    return String(topic || "rule").replace(/_/g, " ");
  }

  function toast(message) {
    els.toast.textContent = message;
    els.toast.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () {
      els.toast.classList.remove("show");
    }, 1800);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    var area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); } catch (e) {}
    area.remove();
    return Promise.resolve();
  }

  function scrollToBottom() {
    els.thread.scrollTop = els.thread.scrollHeight;
  }

  // ============================================================
  // RENDERING
  // ============================================================

  function renderSuggestions() {
    els.suggestions.innerHTML = SUGGESTIONS.map(function (s, i) {
      return '<button class="suggestion" data-index="' + i + '">' +
        '<span class="tag">' + escapeHtml(s.tag) + "</span>" +
        "<span>" + escapeHtml(s.text) + "</span></button>";
    }).join("");
  }

  function renderHistory() {
    if (!conversations.length) {
      els.history.innerHTML = '<li class="history-empty">No conversations yet</li>';
      return;
    }

    els.history.innerHTML = conversations.map(function (c) {
      var active = current && current.id === c.id ? " active" : "";
      return '<li class="' + active.trim() + '" data-id="' + c.id + '">' +
        '<button class="history-title" title="' + escapeHtml(c.title) + '">' +
        escapeHtml(c.title) + "</button>" +
        '<button class="icon-btn history-del" aria-label="Delete conversation">' +
        ICONS.trash + "</button></li>";
    }).join("");
  }

  function renderDocuments(docs) {
    if (!docs.length) {
      els.docList.innerHTML = '<li class="history-empty">No documents found</li>';
      return;
    }

    els.docList.innerHTML = docs.map(function (d) {
      return '<li><a href="' + escapeHtml(d.url) + '" target="_blank" rel="noopener" title="' +
        escapeHtml(d.label + " · " + d.name) + '">' +
        '<span class="dot ' + escapeHtml(d.category) + '"></span>' +
        '<span class="doc-name">' + escapeHtml(prettyName(d.name)) + "</span></a></li>";
    }).join("");
  }

  function userMessage(text) {
    var el = document.createElement("div");
    el.className = "msg user";
    el.innerHTML = '<div class="bubble">' + escapeHtml(text) + "</div>";
    return el;
  }

  function botShell() {
    var el = document.createElement("div");
    el.className = "msg bot";
    el.innerHTML = '<div class="avatar">' + ICONS.bot + '</div><div class="body"></div>';
    return el;
  }

  function sourceCard(c) {
    var page = c.page != null && c.page !== "" ? "Page " + escapeHtml(c.page) : "";
    var open = c.url
      ? '<a class="ghost-btn primary" href="' + escapeHtml(c.url) + '" target="_blank" rel="noopener">' +
        ICONS.external + '<span class="label">Open</span></a>'
      : "";
    var toggle = c.excerpt
      ? '<button class="ghost-btn excerpt-toggle" aria-expanded="false">' +
        '<span class="label">Excerpt</span>' + ICONS.chevron + "</button>"
      : "";

    return '<div class="source">' +
      '<div class="source-head">' +
      '<div class="source-icon">' + ICONS.file + "</div>" +
      '<div class="source-main">' +
      '<div class="source-name" title="' + escapeHtml(c.source) + '">' + escapeHtml(prettyName(c.source)) + "</div>" +
      '<div class="source-meta"><span class="badge ' + escapeHtml(c.category) + '">' +
      escapeHtml(categoryLabel(c.category)) + "</span>" + (page ? "<span>" + page + "</span>" : "") + "</div>" +
      "</div>" +
      '<div class="source-actions">' + toggle + open + "</div>" +
      "</div>" +
      (c.excerpt ? '<div class="excerpt">' + escapeHtml(c.excerpt) + "</div>" : "") +
      "</div>";
  }

  function claimCard(side, controlling) {
    var controls = controlling &&
      String(side.source || "").toLowerCase() === String(controlling).toLowerCase();
    var label = escapeHtml(prettyName(side.source)) +
      (side.page != null && side.page !== "" ? " · p." + escapeHtml(side.page) : "");
    var src = side.url
      ? '<a href="' + escapeHtml(side.url) + '" target="_blank" rel="noopener">' + label + "</a>"
      : label;

    return '<div class="claim' + (controls ? " controls" : "") + '">' +
      '<div class="claim-src" title="' + escapeHtml(side.source) + '">' + src + "</div>" +
      '<div class="claim-text">' + escapeHtml(side.claim || "—") + "</div>" +
      (controls ? '<div class="claim-flag">' + ICONS.check + "Controlling source</div>" : "") +
      "</div>";
  }

  function conflictCard(c) {
    return '<div class="conflict">' +
      '<div class="conflict-head">' + ICONS.warn +
      "Conflicting rule on " + escapeHtml(humanTopic(c.topic)) + "</div>" +
      '<div class="conflict-grid">' +
      claimCard(c.a || {}, c.controlling_source) +
      claimCard(c.b || {}, c.controlling_source) +
      "</div></div>";
  }

  function renderAnswer(body, question, result) {
    var html = "";

    if (result.abstained) {
      html += '<div class="card"><div class="abstain">' + ICONS.info +
        "<div><strong>Not covered by the documents</strong>" +
        "<span>" + escapeHtml(result.answer) +
        " Try rephrasing, or ask about SMCS governance, bylaws or operating procedures.</span></div></div></div>";
    } else {
      html += '<div class="card answer">' + renderMarkdown(result.answer) + "</div>";
    }

    if (result.citations && result.citations.length) {
      html += '<div class="block-label">' + ICONS.book + "Sources</div>" +
        '<div class="sources">' + result.citations.map(sourceCard).join("") + "</div>";
    }

    if (result.conflicts && result.conflicts.length) {
      html += '<div class="block-label">' + ICONS.warn + "Conflicts detected</div>" +
        result.conflicts.map(conflictCard).join("");
    }

    html += '<div class="msg-foot">';
    if (!result.abstained) {
      html += '<button class="ghost-btn copy-btn">' + ICONS.copy + "Copy</button>";
    }
    if (result.trace) {
      html += '<button class="ghost-btn trace-btn">' + ICONS.terminal + "Pipeline trace</button>";
    }
    html += '<span class="spacer"></span>';
    if (result.latency_ms != null) {
      html += '<span title="Response time">' + (result.latency_ms / 1000).toFixed(1) + "s</span>";
    }
    html += "</div>";

    if (result.trace) {
      html += '<pre class="trace">' + escapeHtml(result.trace) + "</pre>";
    }

    body.innerHTML = html;

    var copyBtn = body.querySelector(".copy-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        var text = result.answer;
        if (result.citations && result.citations.length) {
          text += "\n\nSources:\n" + result.citations.map(function (c) {
            return "- " + c.source + (c.page != null ? ", page " + c.page : "");
          }).join("\n");
        }
        copyText(text).then(function () { toast("Answer copied"); });
      });
    }

    var traceBtn = body.querySelector(".trace-btn");
    if (traceBtn) {
      traceBtn.addEventListener("click", function () {
        body.querySelector(".trace").classList.toggle("open");
      });
    }

    body.querySelectorAll(".excerpt-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var card = btn.closest(".source");
        var isOpen = card.classList.toggle("open");
        btn.setAttribute("aria-expanded", String(isOpen));
      });
    });
  }

  function renderError(body, question, message) {
    body.innerHTML = '<div class="card error-card"><div class="abstain">' + ICONS.alert +
      "<div><strong>Something went wrong</strong><span>" + escapeHtml(message) + "</span></div></div></div>" +
      '<div class="msg-foot"><button class="ghost-btn retry-btn">' + ICONS.retry + "Retry</button></div>";

    body.querySelector(".retry-btn").addEventListener("click", function () {
      body.closest(".msg").remove();
      // Drop the failed user message too; ask() re-adds it.
      var last = els.thread.lastElementChild;
      if (last && last.classList.contains("user")) last.remove();
      ask(question);
    });
  }

  function renderTyping(body) {
    body.innerHTML = '<div class="card"><div class="typing">' +
      '<div class="dots"><i></i><i></i><i></i></div>' +
      '<span class="stage">' + STAGES[0] + "</span></div></div>";

    var stage = body.querySelector(".stage");
    var i = 0;
    return setInterval(function () {
      i = Math.min(i + 1, STAGES.length - 1);
      stage.textContent = STAGES[i];
    }, 2600);
  }

  function showConversation(conversation) {
    current = conversation;
    els.thread.querySelectorAll(".msg").forEach(function (m) { m.remove(); });

    if (!conversation || !conversation.messages.length) {
      els.welcome.style.display = "";
      els.title.textContent = "New conversation";
    } else {
      els.welcome.style.display = "none";
      els.title.textContent = conversation.title;

      conversation.messages.forEach(function (m) {
        els.thread.appendChild(userMessage(m.question));
        var bot = botShell();
        els.thread.appendChild(bot);
        renderAnswer(bot.querySelector(".body"), m.question, m.result);
      });
    }

    renderHistory();
    scrollToBottom();
  }

  // ============================================================
  // CHAT
  // ============================================================

  function ask(question) {
    question = question.trim();
    if (!question || busy) return;

    busy = true;
    updateSendState();
    els.welcome.style.display = "none";

    if (!current) {
      current = {
        id: uid(),
        title: question.length > 60 ? question.slice(0, 57) + "…" : question,
        messages: []
      };
      conversations.unshift(current);
      els.title.textContent = current.title;
      renderHistory();
    }

    var conversation = current;

    els.thread.appendChild(userMessage(question));
    var bot = botShell();
    els.thread.appendChild(bot);
    var body = bot.querySelector(".body");
    var timer = renderTyping(body);
    scrollToBottom();

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question })
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            throw new Error(data.detail || ("Request failed (" + res.status + ")"));
          }
          return data;
        });
      })
      .then(function (result) {
        clearInterval(timer);
        conversation.messages.push({ question: question, result: result });

        // Move to top of history.
        conversations = [conversation].concat(conversations.filter(function (c) {
          return c.id !== conversation.id;
        }));
        saveConversations();
        renderHistory();

        if (current === conversation) {
          renderAnswer(body, question, result);
          scrollToBottom();
        }
      })
      .catch(function (err) {
        clearInterval(timer);
        if (!conversation.messages.length) {
          conversations = conversations.filter(function (c) { return c.id !== conversation.id; });
          renderHistory();
        }
        if (current === conversation) {
          renderError(body, question, err.message || "Could not reach the server.");
          scrollToBottom();
        }
      })
      .then(function () {
        busy = false;
        updateSendState();
        els.input.focus();
      });
  }

  function updateSendState() {
    els.send.disabled = busy || !els.input.value.trim();
  }

  function autosize() {
    els.input.style.height = "auto";
    els.input.style.height = Math.min(els.input.scrollHeight, 200) + "px";
  }

  // ============================================================
  // STATUS
  // ============================================================

  function setStatus(state, text) {
    els.status.className = "status " + state;
    els.status.querySelector(".status-text").textContent = text;
  }

  function pollHealth() {
    fetch("/api/health")
      .then(function (r) { return r.json(); })
      .then(function (h) {
        if (h.status === "ready") {
          setStatus("ready", h.demo ? "Demo mode" : "Ready");
        } else if (h.status === "error") {
          setStatus("error", "Pipeline error");
          els.status.title = h.error || "";
        } else {
          setStatus("loading", "Loading models…");
          setTimeout(pollHealth, 2500);
        }
      })
      .catch(function () {
        setStatus("error", "Offline");
        setTimeout(pollHealth, 5000);
      });
  }

  function loadDocuments() {
    fetch("/api/documents")
      .then(function (r) { return r.json(); })
      .then(renderDocuments)
      .catch(function () { renderDocuments([]); });
  }

  // ============================================================
  // THEME & LAYOUT
  // ============================================================

  function effectiveTheme() {
    var set = document.documentElement.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  }

  function toggleTheme() {
    var next = effectiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
  }

  function openSidebar(open) {
    els.sidebar.classList.toggle("open", open);
  }

  // ============================================================
  // EVENTS
  // ============================================================

  els.composer.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = els.input.value;
    if (!q.trim() || busy) return;
    els.input.value = "";
    autosize();
    ask(q);
  });

  els.input.addEventListener("input", function () {
    autosize();
    updateSendState();
  });

  els.input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      els.composer.requestSubmit();
    }
  });

  els.suggestions.addEventListener("click", function (e) {
    var btn = e.target.closest(".suggestion");
    if (btn) ask(SUGGESTIONS[+btn.dataset.index].text);
  });

  els.newChat.addEventListener("click", function () {
    showConversation(null);
    openSidebar(false);
    els.input.focus();
  });

  els.history.addEventListener("click", function (e) {
    var li = e.target.closest("li[data-id]");
    if (!li) return;
    var id = li.dataset.id;

    if (e.target.closest(".history-del")) {
      conversations = conversations.filter(function (c) { return c.id !== id; });
      saveConversations();
      if (current && current.id === id) showConversation(null);
      else renderHistory();
      return;
    }

    var found = conversations.find(function (c) { return c.id === id; });
    if (found && !busy) {
      showConversation(found);
      openSidebar(false);
    }
  });

  els.themeToggle.addEventListener("click", toggleTheme);
  els.menuBtn.addEventListener("click", function () { openSidebar(true); });
  els.sidebarClose.addEventListener("click", function () { openSidebar(false); });
  els.scrim.addEventListener("click", function () { openSidebar(false); });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") openSidebar(false);
  });

  // ============================================================
  // INIT
  // ============================================================

  renderSuggestions();
  showConversation(null);
  loadDocuments();
  pollHealth();
  els.input.focus();
})();
