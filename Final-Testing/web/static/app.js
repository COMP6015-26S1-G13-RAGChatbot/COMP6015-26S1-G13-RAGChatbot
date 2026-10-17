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
    external: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
    chevron: '<svg class="chev" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>',
    trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>'
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
    themeSwitch: $("themeSwitch"),
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
    return String(topic || "rule").replace(/_/g, " ").replace(/\bbog\b/gi, "BoG");
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
        '<span class="s-text">' + escapeHtml(s.text) + "</span></button>";
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
        escapeHtml(d.label + ": " + d.name) + '">' +
        '<span class="dot ' + escapeHtml(d.category) + '"></span>' +
        '<span class="doc-name">' + escapeHtml(prettyName(d.name)) + "</span></a></li>";
    }).join("");

    var corpus = $("corpus");
    if (corpus) {
      var counts = {};
      docs.forEach(function (d) { counts[d.category] = (counts[d.category] || 0) + 1; });
      corpus.textContent = docs.length + " documents indexed: " + Object.keys(counts).map(function (k) {
        return counts[k] + " " + k;
      }).join(", ") + ".";
    }
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
    el.innerHTML = '<div class="body"></div>';
    return el;
  }

  function sourceCard(c, i) {
    var page = c.page != null && c.page !== "" ? "p. " + escapeHtml(c.page) : "";
    var open = c.url
      ? '<a class="ghost-btn primary" href="' + escapeHtml(c.url) + '" target="_blank" rel="noopener">' +
        '<span class="label">Open PDF</span>' + ICONS.external + "</a>"
      : "";
    var toggle = c.excerpt
      ? '<button class="ghost-btn excerpt-toggle" aria-expanded="false">' +
        '<span class="label">Quoted text</span>' + ICONS.chevron + "</button>"
      : "";

    return '<li class="source">' +
      '<div class="source-head">' +
      '<span class="source-num">[' + ((i || 0) + 1) + "]</span>" +
      '<div class="source-main">' +
      '<div class="source-name" title="' + escapeHtml(c.source) + '">' + escapeHtml(prettyName(c.source)) +
      (page ? '<span class="source-page">, ' + page + "</span>" : "") + "</div>" +
      '<div class="source-meta"><span class="badge ' + escapeHtml(c.category) + '">' +
      escapeHtml(categoryLabel(c.category)) + "</span></div>" +
      "</div>" +
      '<div class="source-actions">' + toggle + open + "</div>" +
      "</div>" +
      (c.excerpt ? '<blockquote class="excerpt">' + escapeHtml(c.excerpt) + "</blockquote>" : "") +
      "</li>";
  }

  function claimCard(side, controlling) {
    var controls = controlling &&
      String(side.source || "").toLowerCase() === String(controlling).toLowerCase();
    var label = escapeHtml(prettyName(side.source)) +
      (side.page != null && side.page !== "" ? ", p. " + escapeHtml(side.page) : "");
    var src = side.url
      ? '<a href="' + escapeHtml(side.url) + '" target="_blank" rel="noopener">' + label + "</a>"
      : label;

    return '<div class="claim' + (controls ? " controls" : "") + '">' +
      '<div class="claim-src" title="' + escapeHtml(side.source) + '">' + src + "</div>" +
      '<div class="claim-text">' + escapeHtml(side.claim || "—") + "</div>" +
      '<div class="claim-flag">' + (controls ? "Takes precedence" : "") + "</div>" +
      "</div>";
  }

  function conflictCard(c) {
    return '<div class="conflict">' +
      '<div class="conflict-head">The documents disagree on: <strong>' +
      escapeHtml(humanTopic(c.topic)) + "</strong></div>" +
      '<div class="conflict-grid">' +
      '<div class="conflict-cols"><span>Document</span><span>States</span><span></span></div>' +
      claimCard(c.a || {}, c.controlling_source) +
      claimCard(c.b || {}, c.controlling_source) +
      "</div></div>";
  }

  function renderAnswer(body, question, result) {
    var html = "";

    if (result.abstained) {
      html += '<div class="card"><div class="abstain">' +
        "<div><strong>Not found in the documents</strong>" +
        "<span>" + escapeHtml(result.answer) +
        " Try rephrasing, or ask about SMCS governance, bylaws or operating procedures.</span></div></div></div>";
    } else {
      html += '<div class="card answer">' + renderMarkdown(result.answer) + "</div>";
    }

    if (result.citations && result.citations.length) {
      html += '<div class="block-label">Sources</div>' +
        '<ol class="sources">' + result.citations.map(sourceCard).join("") + "</ol>";
    }

    if (result.conflicts && result.conflicts.length) {
      html += '<div class="block-label">Conflicting documents</div>' +
        result.conflicts.map(conflictCard).join("");
    }

    html += '<div class="msg-foot">';
    if (!result.abstained) {
      html += '<button class="ghost-btn copy-btn">Copy answer</button>';
    }
    if (result.trace) {
      html += '<button class="ghost-btn trace-btn">Show pipeline log</button>';
    }
    html += '<span class="spacer"></span>';
    if (result.latency_ms != null) {
      html += '<span class="latency" title="Response time">' + (result.latency_ms / 1000).toFixed(1) + " s</span>";
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
        var open = body.querySelector(".trace").classList.toggle("open");
        traceBtn.textContent = open ? "Hide pipeline log" : "Show pipeline log";
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
    body.innerHTML = '<div class="card error-card"><div class="abstain">' +
      "<div><strong>Something went wrong</strong><span>" + escapeHtml(message) + "</span></div></div></div>" +
      '<div class="msg-foot"><button class="ghost-btn retry-btn">Try again</button></div>';

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
      '<div class="progress"><i></i></div>' +
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
    if (conversation && conversation.messages.length) scrollToBottom();
    else els.thread.scrollTop = 0;
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

    function send() {
      return fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question })
      }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          // Still loading: wait for the pipeline, then send again.
          if (res.status === 503 && /still loading/i.test(data.detail || "")) {
            return waitUntilReady(body, timer).then(send);
          }
          if (!res.ok) {
            throw new Error(data.detail || ("Request failed (" + res.status + ")"));
          }
          return data;
        });
      });
    }

    waitUntilReady(body, timer)
      .then(send)
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

  // Resolves once the pipeline has loaded, showing progress in the
  // typing indicator meanwhile. Rejects if loading failed.
  function waitUntilReady(body, timer) {
    return new Promise(function (resolve, reject) {
      function check() {
        fetch("/api/health")
          .then(function (r) { return r.json(); })
          .then(function (h) {
            if (h.status === "ready") {
              setStatus("ready", h.demo ? "Demo mode" : "Ready");
              var ready = body.querySelector(".stage");
              if (ready && /Loading the models/.test(ready.textContent)) {
                ready.textContent = "Models loaded. Generating a grounded answer…";
              }
              return resolve();
            }
            if (h.status === "error") {
              setStatus("error", "Pipeline error");
              return reject(new Error("The pipeline failed to load: " + (h.error || "unknown error") +
                ". Check the terminal running the server for details."));
            }
            clearInterval(timer);
            var stage = body.querySelector(".stage");
            if (stage) {
              stage.textContent = "Loading the models (" + h.loading_seconds +
                "s). Your question will be sent automatically when ready…";
            }
            setTimeout(check, 2000);
          })
          .catch(function () {
            reject(new Error("Could not reach the server. Is the terminal running uvicorn still open?"));
          });
      }
      check();
    });
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
          setStatus("loading", "Loading models… " + h.loading_seconds + "s");
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

  var systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  function themePreference() {
    try { return localStorage.getItem(THEME_KEY) || "system"; } catch (e) { return "system"; }
  }

  function applyTheme(pref) {
    var theme = pref === "system" ? (systemDark.matches ? "dark" : "light") : pref;
    var root = document.documentElement;

    root.classList.add("theme-changing");
    root.setAttribute("data-theme", theme);
    setTimeout(function () { root.classList.remove("theme-changing"); }, 350);

    els.themeSwitch.setAttribute("data-pref", pref);
    els.themeSwitch.querySelectorAll("button").forEach(function (b) {
      b.setAttribute("aria-checked", String(b.dataset.themeValue === pref));
    });
  }

  function setTheme(pref) {
    try { localStorage.setItem(THEME_KEY, pref); } catch (e) {}
    applyTheme(pref);
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

  els.themeSwitch.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-theme-value]");
    if (btn) setTheme(btn.dataset.themeValue);
  });

  var onSystemChange = function () {
    if (themePreference() === "system") applyTheme("system");
  };
  if (systemDark.addEventListener) systemDark.addEventListener("change", onSystemChange);
  else if (systemDark.addListener) systemDark.addListener(onSystemChange);
  els.menuBtn.addEventListener("click", function () { openSidebar(true); });
  els.sidebarClose.addEventListener("click", function () { openSidebar(false); });
  els.scrim.addEventListener("click", function () { openSidebar(false); });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") openSidebar(false);
  });

  // ============================================================
  // INIT
  // ============================================================

  applyTheme(themePreference());
  renderSuggestions();
  showConversation(null);
  loadDocuments();
  pollHealth();
  els.input.focus();
})();
