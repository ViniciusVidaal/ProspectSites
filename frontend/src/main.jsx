import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Archive, ArchiveRestore, Building2, CalendarDays, Check, ExternalLink, Instagram, LoaderCircle, MapPin,
  Clock, MapPinned, MessageCircle, Moon, Pause, Play, Radar, RotateCcw,
  Search, Star, Sun, Trash2, Users, X, ListFilter, Settings, KeyRound, AlertTriangle, Menu, History, Undo2
} from "lucide-react";
import { NICHE_CATEGORIES } from "./niches";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const LEADS_CACHE = "prospect-leads-cache";
const STATS_CACHE = "prospect-stats-cache";
const MESSAGE_CACHE = "prospect-message-template";
const DEFAULT_MESSAGE = `Opa, **[Empresa]**. Estava analisando o perfil de vocês no Google e vi que vocês já conquistaram **[AVALIAÇÕES] avaliações** e mantêm uma nota de **[NOTA]⭐** no Google. Mas notei um problema grave: vocês estão perdendo clientes todos os dias por não ter um site oficial.

Muita gente acha a empresa no mapa, procura o site pra confirmar a credibilidade e, como não acha, fecha com a concorrência.

Eu resolvo exatamente isso. Crio sites profissionais focados em vendas por apenas R$ 497 (pagamento único), e ainda libero 1 ano de hospedagem grátis pra vocês.

Posso montar uma prévia do site da **[Empresa]** sem compromisso pra você ver na prática?`;

function readCache(key, fallback) {
  try {
    const cached = JSON.parse(localStorage.getItem(key));
    return cached ?? fallback;
  } catch {
    return fallback;
  }
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function readableError(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg || "Dados inválidos").join(" · ");
  return detail?.message || "Não foi possível concluir.";
}

async function api(path, options) {
  const isRead = !options?.method || options.method === "GET";
  const separator = path.includes("?") ? "&" : "?";
  const requestPath = isRead ? `${path}${separator}_=${Date.now()}` : path;
  const response = await fetch(`${API}${requestPath}`, {
    ...options,
    cache: isRead ? "no-store" : undefined,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
  });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(readableError(body.detail));
    error.status = response.status;
    throw error;
  }
  return body;
}

function App() {
  const [leads, setLeads] = useState(() => readCache(LEADS_CACHE, []));
  const [mode, setMode] = useState("free");
  const [activeView, setActiveView] = useState("prospecting");
  const [query, setQuery] = useState("");
  const [selectedNiche, setSelectedNiche] = useState("");
  const [location, setLocation] = useState("");
  const [category, setCategory] = useState("");
  const [minimumReviews, setMinimumReviews] = useState(50);
  const [dateFilter, setDateFilter] = useState("all");
  const [theme, setTheme] = useState(
    () => localStorage.getItem("prospect-theme") || "light"
  );
  const [message, setMessage] = useState(
    () => localStorage.getItem(MESSAGE_CACHE) ?? DEFAULT_MESSAGE
  );
  const [messageDraft, setMessageDraft] = useState(message);
  const [messageSaving, setMessageSaving] = useState(false);
  const [job, setJob] = useState(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(() => !localStorage.getItem(LEADS_CACHE));
  const [stats, setStats] = useState(() => readCache(STATS_CACHE, { archived: 0, sent: 0, sent_today: 0 }));
  const [sendMode, setSendMode] = useState("manual");
  const [sessionAmount, setSessionAmount] = useState(5);
  const [batchSize, setBatchSize] = useState(5);
  const [messageIntervalMin, setMessageIntervalMin] = useState(1);
  const [messageIntervalMax, setMessageIntervalMax] = useState(10);
  const [batchPause, setBatchPause] = useState(10);
  const [dispatch, setDispatch] = useState(null);
  const [clock, setClock] = useState(Date.now());
  const [leadActions, setLeadActions] = useState({});
  const [messageOpen, setMessageOpen] = useState(false);
  const [historyLeads, setHistoryLeads] = useState([]);
  const [deletionHistoryLoading, setDeletionHistoryLoading] = useState(false);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyStartDate, setHistoryStartDate] = useState("");
  const [historyEndDate, setHistoryEndDate] = useState("");
  const [historyPeriod, setHistoryPeriod] = useState("all");
  const [historyPage, setHistoryPage] = useState(0);
  const [historyCursors, setHistoryCursors] = useState([null]);
  const [historyNextCursor, setHistoryNextCursor] = useState(null);
  const [apiKeys, setApiKeys] = useState([]);
  const [apiName, setApiName] = useState("");
  const [apiValue, setApiValue] = useState("");
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsNotice, setSettingsNotice] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [deletedLeads, setDeletedLeads] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const dispatchWindowRef = useRef(null);

  const loadLeads = async ({ silent = false, retries = 1, refreshStats = false } = {}) => {
    let lastError;
    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        // The API is the shared source of truth.  localStorage is retained only
        // as a temporary offline fallback and must never cap the shared base.
        const leadItems = await api("/api/leads?include_archived=false&pending_only=true&limit=100");
        setLeads(leadItems);
        localStorage.setItem(LEADS_CACHE, JSON.stringify(leadItems));
        if (refreshStats) {
          try {
            const metrics = await api("/api/stats");
            setStats(metrics);
            localStorage.setItem(STATS_CACHE, JSON.stringify(metrics));
          } catch {
            // A fila foi atualizada; as métricas serão renovadas na próxima abertura.
          }
        }
        setNotice("");
        setLoading(false);
        return;
      } catch (error) {
        lastError = error;
        // Retrying a Firebase quota response only consumes more reads and does
        // not make the dashboard more current.
        if (error.status === 429) break;
        if (attempt < retries) await wait(Math.min(2000 + attempt * 1500, 8000));
      }
    }
    if (!silent) setNotice(lastError?.message || "Não foi possível atualizar os leads.");
    setLoading(false);
  };

  const loadMessageTemplate = async ({ silent = true } = {}) => {
    try {
      const result = await api("/api/settings/message-template");
      const sharedMessage = String(result.message || "").trim();
      if (!sharedMessage) return;
      setMessage(sharedMessage);
      setMessageDraft(sharedMessage);
      localStorage.setItem(MESSAGE_CACHE, sharedMessage);
    } catch (error) {
      if (!silent) setNotice(error.message);
    }
  };

  useEffect(() => {
    const refresh = () => {
      loadLeads({ silent: true, retries: 1 });
      loadMessageTemplate();
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") refresh();
    };

    loadLeads({ silent: leads.length > 0, refreshStats: true });
    loadMessageTemplate();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const isoDate = (date) => date.toISOString().slice(0, 10);
  const formatDate = (value) => {
    if (!value) return "—";
    const [year, month, day] = value.split("-");
    return year && month && day ? `${day}/${month}/${year}` : value;
  };

  const applyHistoryPeriod = (period) => {
    setHistoryPeriod(period);
    if (period === "all") {
      setHistoryStartDate("");
      setHistoryEndDate("");
      return;
    }
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - (Number(period) - 1));
    setHistoryStartDate(isoDate(start));
    setHistoryEndDate(isoDate(end));
  };

  const loadHistory = async ({ silent = false, cursor = null } = {}) => {
    setHistoryLoading(true);
    try {
      const params = new URLSearchParams();
      if (historyQuery.trim()) params.set("query", historyQuery.trim());
      if (historyStartDate) params.set("start_date", historyStartDate);
      if (historyEndDate) params.set("end_date", historyEndDate);
      params.set("limit", "20");
      if (cursor) params.set("cursor", cursor);
      const result = await api(`/api/leads/history?${params.toString()}`);
      setHistoryLeads(result.items || []);
      setHistoryNextCursor(result.next_cursor || null);
      if (!silent) setNotice("");
    } catch (error) {
      setNotice(error.message);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    applyHistoryPeriod("all");
  }, []);

  useEffect(() => {
    if (activeView !== "leads" || !historyEndDate) return;
    setHistoryPage(0);
    setHistoryCursors([null]);
    loadHistory({ silent: true, cursor: null });
  }, [activeView, historyStartDate, historyEndDate]);

  const changeHistoryPage = (direction) => {
    if (direction === "next" && historyNextCursor) {
      const nextPage = historyPage + 1;
      setHistoryCursors((current) => [...current.slice(0, nextPage), historyNextCursor]);
      setHistoryPage(nextPage);
      loadHistory({ cursor: historyNextCursor });
    } else if (direction === "previous" && historyPage > 0) {
      const previousPage = historyPage - 1;
      setHistoryPage(previousPage);
      loadHistory({ cursor: historyCursors[previousPage] });
    }
  };

  const loadApiKeys = async () => {
    setSettingsLoading(true);
    try { setApiKeys(await api("/api/settings/api-keys")); }
    catch (error) { setSettingsNotice(error.message); }
    finally { setSettingsLoading(false); }
  };

  useEffect(() => { if (activeView === "settings") loadApiKeys(); }, [activeView]);

  const loadDeletionHistory = async () => {
    setDeletionHistoryLoading(true);
    try { setDeletedLeads(await api("/api/history/deletions")); }
    catch (error) { setNotice(error.message); }
    finally { setDeletionHistoryLoading(false); }
  };

  useEffect(() => { if (activeView === "history") loadDeletionHistory(); }, [activeView]);

  const saveApiKey = async (event) => {
    event.preventDefault();
    setSettingsLoading(true);
    try {
      await api("/api/settings/api-keys", { method: "POST", body: JSON.stringify({ name: apiName, api_key: apiValue, make_active: true }) });
      setApiName(""); setApiValue(""); setSettingsNotice("API salva e ativada com sucesso."); await loadApiKeys();
    } catch (error) { setSettingsNotice(error.message); }
    finally { setSettingsLoading(false); }
  };

  const activateApiKey = async (key) => {
    setSettingsLoading(true);
    try { await api(`/api/settings/api-keys/${encodeURIComponent(key.id)}/activate`, { method: "POST" }); setSettingsNotice(`${key.name} está ativa agora.`); await loadApiKeys(); }
    catch (error) { setSettingsNotice(error.message); }
    finally { setSettingsLoading(false); }
  };

  const deleteApiKey = async (key) => {
    if (!window.confirm(`Excluir a API "${key.name}"? Essa ação não pode ser desfeita.`)) return;
    setSettingsLoading(true);
    try {
      const result = await api(`/api/settings/api-keys/${encodeURIComponent(key.id)}`, { method: "DELETE" });
      setSettingsNotice(result.activated_name ? `API excluída. ${result.activated_name} está ativa agora.` : "API excluída com sucesso.");
      await loadApiKeys();
    } catch (error) { setSettingsNotice(error.message); }
    finally { setSettingsLoading(false); }
  };

  const chooseView = (view) => { setActiveView(view); setSidebarOpen(false); };
  const toggleSidebar = () => {
    if (window.innerWidth <= 700) setSidebarOpen(true);
    else setSidebarCollapsed((current) => !current);
  };

  const restoreLead = async (lead) => {
    if (!window.confirm(`Restaurar ${lead.company_name} para a base de leads?`)) return;
    try {
      await api(`/api/leads/${encodeURIComponent(lead.place_id)}/restore`, { method: "POST" });
      await Promise.all([loadDeletionHistory(), loadLeads({ silent: true })]);
    } catch (error) { setNotice(error.message); }
  };

  useEffect(() => {
    localStorage.setItem(LEADS_CACHE, JSON.stringify(leads));
  }, [leads]);

  useEffect(() => {
    localStorage.setItem(STATS_CACHE, JSON.stringify(stats));
  }, [stats]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("prospect-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!job || ["completed", "failed"].includes(job.status)) return;
    const timer = setInterval(async () => {
      try {
        const current = await api(`/api/jobs/${job.id}`);
        setJob(current);
        if (["completed", "failed"].includes(current.status)) loadLeads({ refreshStats: true });
      } catch (error) {
        setNotice(error.message);
        setJob((current) => current ? { ...current, status: "failed", detail: error.message } : current);
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [job?.id, job?.status]);

  const today = new Intl.DateTimeFormat("pt-BR").format(new Date());
  const visible = useMemo(
    () => leads
      .filter((lead) => !lead.archived)
      .filter((lead) => !lead.sent && !leadActions[lead.place_id])
      .filter((lead) => dateFilter === "all" || lead.date === today)
      .sort((a, b) =>
        Number(b.review_count || 0) - Number(a.review_count || 0)
        || Number(b.rating || 0) - Number(a.rating || 0)
        || a.company_name.localeCompare(b.company_name, "pt-BR")
      ),
    [leads, leadActions, dateFilter, today]
  );
  const sentCount = leads.filter((lead) => lead.sent && !lead.archived).length;
  const busy = job && !["completed", "failed"].includes(job.status);

  const search = async (event) => {
    event.preventDefault();
    const finalQuery = mode === "free"
      ? query.trim()
      : [selectedNiche, location].filter(Boolean).join(" ").trim();
    if (finalQuery.length < 2) return setNotice("Preencha os dados da pesquisa.");
    setNotice("");
    try {
      setJob(await api("/api/search", {
        method: "POST",
        body: JSON.stringify({
          query: finalQuery,
          minimum_reviews: Number(minimumReviews),
        }),
      }));
    } catch (error) { setNotice(error.message); }
  };

  const whatsappHref = (lead) => {
    if (!lead.whatsapp_link) return "";
    const phone = lead.whatsapp_link.match(/wa\.me\/(\d+)/)?.[1]
      || lead.phone.replace(/\D/g, "");
    const reviewCount = Number(lead.review_count || 0).toLocaleString("pt-BR");
    const rating = Number(lead.rating || 0).toLocaleString("pt-BR", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
    const personalizedMessage = message
      .replace(/\[empresa\]/gi, lead.company_name)
      .replace(/\[avaliações\]/gi, reviewCount)
      .replace(/\[nota\]/gi, rating)
      .trim();
    return `whatsapp://send?phone=${phone}&text=${encodeURIComponent(personalizedMessage)}`;
  };

  const cnpjWhatsappHref = (lead) => {
    const phone = String(lead.cnpj_phone || "").replace(/\D/g, "");
    if (!phone) return "";
    const personalizedMessage = message
      .replace(/\[empresa\]/gi, lead.company_name)
      .replace(/\[avaliações\]/gi, Number(lead.review_count || 0).toLocaleString("pt-BR"))
      .replace(/\[nota\]/gi, Number(lead.rating || 0).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }))
      .trim();
    return `whatsapp://send?phone=${phone}&text=${encodeURIComponent(personalizedMessage)}`;
  };

  const markSent = async (placeId) => {
    const original = leads.find((lead) => lead.place_id === placeId);
    if (!original || original.sent || leadActions[placeId]) return false;
    setLeadActions((current) => ({ ...current, [placeId]: "sending" }));
    setLeads((items) => items.map((lead) =>
      lead.place_id === placeId ? { ...lead, sent: true } : lead
    ));
    setStats((current) => ({
      ...current,
      sent: Number(current.sent || 0) + 1,
      sent_today: Number(current.sent_today || 0) + 1,
    }));
    try {
      const updated = await api(`/api/leads/${encodeURIComponent(placeId)}/sent`, { method: "POST", keepalive: true });
      setLeads((items) => items.map((lead) => lead.place_id === placeId ? { ...lead, ...updated } : lead));
      if (updated.already_sent) {
        setStats((current) => ({
          ...current,
          sent: Math.max(0, Number(current.sent || 0) - 1),
          sent_today: Math.max(0, Number(current.sent_today || 0) - 1),
        }));
        setNotice("Este lead já havia sido enviado em outra sessão e não será aberto novamente.");
        return false;
      }
      return true;
    } catch (error) {
      setLeads((items) => items.map((lead) =>
        lead.place_id === placeId ? original : lead
      ));
      setStats((current) => ({
        ...current,
        sent: Math.max(0, Number(current.sent || 0) - 1),
        sent_today: Math.max(0, Number(current.sent_today || 0) - 1),
      }));
      setNotice(`O WhatsApp foi aberto, mas o envio não foi registrado: ${error.message}`);
      return false;
    } finally {
      setLeadActions((current) => {
        const next = { ...current };
        delete next[placeId];
        return next;
      });
    }
  };

  const openLeadContact = async (event, lead, href) => {
    event.preventDefault();
    if (!href || leadActions[lead.place_id] || lead.sent) return;
    const contactWindow = window.open("about:blank", "_blank");
    if (!contactWindow) {
      setNotice("O navegador bloqueou a abertura do contato. Permita pop-ups para este site e tente novamente.");
      return;
    }
    const recorded = await markSent(lead.place_id);
    if (!recorded) {
      contactWindow.close();
      return;
    }
    contactWindow.location.replace(href);
  };

  const changeSentStatus = async (lead, sent) => {
    if (leadActions[lead.place_id]) return;
    const original = lead;
    setLeadActions((current) => ({ ...current, [lead.place_id]: "status" }));
    setLeads((items) => items.map((item) =>
      item.place_id === lead.place_id ? { ...item, sent, sent_at: sent ? item.sent_at : "" } : item
    ));
    const wasSentToday = lead.sent && String(lead.sent_at || "").startsWith(today);
    setStats((current) => ({
      ...current,
      sent: Math.max(0, Number(current.sent || 0) + (sent ? 1 : -1)),
      sent_today: Math.max(0, Number(current.sent_today || 0) + (sent ? 1 : wasSentToday ? -1 : 0)),
    }));
    try {
      const updated = await api(`/api/leads/${encodeURIComponent(lead.place_id)}/sent-status`, {
        method: "POST",
        body: JSON.stringify({ sent }),
        keepalive: true,
      });
      setLeads((items) => items.map((item) =>
        item.place_id === lead.place_id ? { ...item, ...updated } : item
      ));
    } catch (error) {
      setLeads((items) => items.map((item) => item.place_id === lead.place_id ? original : item));
      setStats((current) => ({
        ...current,
        sent: Math.max(0, Number(current.sent || 0) + (sent ? -1 : 1)),
        sent_today: Math.max(0, Number(current.sent_today || 0) + (sent ? -1 : wasSentToday ? 1 : 0)),
      }));
      setNotice(`Não foi possível alterar o status: ${error.message}`);
    } finally {
      setLeadActions((current) => {
        const next = { ...current };
        delete next[lead.place_id];
        return next;
      });
    }
  };

  const saveMessage = async () => {
    const normalized = messageDraft.trim();
    if (!normalized) return setNotice("A mensagem personalizada não pode ficar vazia.");
    setMessageSaving(true);
    try {
      const result = await api("/api/settings/message-template", {
        method: "PUT",
        body: JSON.stringify({ message: normalized }),
      });
      const savedMessage = String(result.message || normalized);
      setMessage(savedMessage);
      setMessageDraft(savedMessage);
      localStorage.setItem(MESSAGE_CACHE, savedMessage);
      setNotice("Mensagem salva e sincronizada entre dispositivos.");
    } catch (error) {
      setNotice(`Não foi possível salvar a mensagem: ${error.message}`);
    } finally {
      setMessageSaving(false);
    }
  };

  const deleteLead = async (lead) => {
    if (!window.confirm(`Excluir ${lead.company_name} do painel? O histórico continuará protegido para evitar leads repetidos.`)) return;
    if (leadActions[lead.place_id]) return;
    const previousLeads = leads;
    setLeadActions((current) => ({ ...current, [lead.place_id]: "archiving" }));
    setLeads((items) => items.filter((item) => item.place_id !== lead.place_id));
    setStats((current) => ({
      ...current,
      active: Math.max(0, Number(current.active || 0) - 1),
      archived: Number(current.archived || 0) + 1,
    }));
    try {
      await api(`/api/leads/${encodeURIComponent(lead.place_id)}`, { method: "DELETE" });
    } catch (error) {
      setLeads(previousLeads);
      setStats((current) => ({
        ...current,
        active: Number(current.active || 0) + 1,
        archived: Math.max(0, Number(current.archived || 0) - 1),
      }));
      setNotice(`Não foi possível excluir o lead do painel: ${error.message}`);
    } finally {
      setLeadActions((current) => {
        const next = { ...current };
        delete next[lead.place_id];
        return next;
      });
    }
  };

  const archiveToday = async () => {
    const todayLeads = leads.filter((lead) => lead.date === today && !lead.archived);
    if (!todayLeads.length) return setNotice("Não há leads de hoje para arquivar.");
    if (!window.confirm(`Arquivar os ${todayLeads.length} lead(s) de hoje? Eles continuarão salvos no histórico.`)) return;
    const previous = leads;
    const ids = todayLeads.map((lead) => lead.place_id);
    setLeads((items) => items.filter((lead) => lead.date !== today));
    try {
      await api("/api/leads/archive", {
        method: "POST",
        body: JSON.stringify({ place_ids: ids }),
      });
      await loadLeads();
    } catch (error) {
      setLeads(previous);
      setNotice(`Não foi possível arquivar os leads de hoje: ${error.message}`);
    }
  };

  const archiveSent = async () => {
    const sentLeads = leads.filter((lead) => lead.sent && !lead.archived);
    if (!sentLeads.length) return setNotice("Não há leads enviados para arquivar.");
    if (!window.confirm(`Arquivar os ${sentLeads.length} lead(s) já enviados? Eles continuarão salvos no histórico.`)) return;
    const previous = leads;
    const ids = sentLeads.map((lead) => lead.place_id);
    setLeads((items) => items.filter((lead) => !lead.sent));
    try {
      await api("/api/leads/archive", {
        method: "POST",
        body: JSON.stringify({ place_ids: ids }),
      });
      await loadLeads();
    } catch (error) {
      setLeads(previous);
      setNotice(`Não foi possível arquivar os leads enviados: ${error.message}`);
    }
  };

  const startDispatch = () => {
    const queue = leads
      .filter((lead) => !lead.sent && lead.whatsapp_link)
      .slice(0, Math.max(1, Number(sessionAmount) || 1));
    if (!queue.length) return setNotice("Não há leads pendentes com WhatsApp para iniciar a sessão.");
    const whatsappWindow = window.open("about:blank", "prospect-whatsapp-session");
    if (!whatsappWindow) {
      return setNotice("O navegador bloqueou o iniciador do WhatsApp. Permita pop-ups para este site e tente novamente.");
    }
    dispatchWindowRef.current = whatsappWindow;
    setNotice("");
    advanceDispatch({ queue, index: 0, sentInBatch: 0, status: "ready", nextAt: 0 }, whatsappWindow);
  };

  const advanceDispatch = async (session = dispatch, targetWindow = dispatchWindowRef.current) => {
    if (!session || session.index >= session.queue.length) return;
    if (!targetWindow || targetWindow.closed) {
      setNotice("A janela do WhatsApp Web foi fechada. Inicie uma nova sessão.");
      setDispatch({ ...session, status: "paused", pausedRemaining: 0 });
      return;
    }
    const lead = session.queue[session.index];
    const recorded = await markSent(lead.place_id);
    if (!recorded) {
      setDispatch({ ...session, status: "paused", pausedRemaining: 0 });
      return;
    }
    targetWindow.location.href = whatsappHref(lead);
    const nextIndex = session.index + 1;
    const nextBatchCount = session.sentInBatch + 1;
    if (nextIndex >= session.queue.length) {
      setDispatch({ ...session, index: nextIndex, sentInBatch: nextBatchCount, status: "completed", nextAt: 0 });
      return;
    }
    const closesBatch = nextBatchCount >= Math.max(1, Number(batchSize) || 1);
    const minimumSeconds = Math.max(0, Number(messageIntervalMin) || 0) * 60;
    const maximumSeconds = Math.max(minimumSeconds, Math.max(0, Number(messageIntervalMax) || 0) * 60);
    const randomSeconds = Math.floor(
      minimumSeconds + Math.random() * (maximumSeconds - minimumSeconds + 1)
    );
    const waitingSeconds = closesBatch
      ? Math.max(0, Number(batchPause) || 0) * 60
      : randomSeconds;
    const nextAt = Date.now() + waitingSeconds * 1000;
    setClock(Date.now());
    setDispatch({
      ...session,
      index: nextIndex,
      sentInBatch: closesBatch ? 0 : nextBatchCount,
      status: "waiting",
      nextAt,
      waitingType: closesBatch ? "batch" : "message",
    });
  };

  const remainingSeconds = dispatch?.status === "waiting"
    ? Math.max(0, Math.ceil((dispatch.nextAt - clock) / 1000))
    : 0;
  const dispatchReady = dispatch?.status === "waiting" && remainingSeconds === 0;
  const countdownLabel = `${String(Math.floor(remainingSeconds / 60)).padStart(2, "0")}:${String(remainingSeconds % 60).padStart(2, "0")}`;

  useEffect(() => {
    if (!dispatch || dispatch.status !== "waiting") return;
    const tick = setInterval(() => setClock(Date.now()), 1000);
    const delay = Math.max(0, dispatch.nextAt - Date.now());
    const nextLead = setTimeout(() => advanceDispatch(dispatch), delay);
    return () => {
      clearInterval(tick);
      clearTimeout(nextLead);
    };
  }, [dispatch?.status, dispatch?.nextAt, dispatch?.index]);

  return (
    <main className={`app-shell ${sidebarCollapsed ? "sidebar-is-collapsed" : ""}`}>
      <nav className={`sidebar ${sidebarOpen ? "open" : ""} ${sidebarCollapsed ? "collapsed" : ""}`} aria-label="Navegação principal"><a className="brand" href="#" onClick={() => chooseView("prospecting")}><span><Radar size={20}/></span>Prospect Sites</a><div className="sidebar-links"><button className={activeView === "prospecting" ? "active" : ""} onClick={() => chooseView("prospecting")} title="Prospectar"><Radar size={17}/>Prospectar</button><button onClick={() => { setMessageDraft(message); setMessageOpen(true); setSidebarOpen(false); }} title="Mensagem"><MessageCircle size={17}/>Mensagem</button><button className={activeView === "settings" ? "active" : ""} onClick={() => chooseView("settings")} title="Configurações"><Settings size={17}/>Configurações</button></div></nav>{sidebarOpen && <button className="sidebar-backdrop" aria-label="Fechar menu" onClick={() => setSidebarOpen(false)} />}
      <div className="app-content"><header className="topbar"><button className="menu-toggle" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "Abrir menu" : "Recolher menu"}><Menu size={20}/></button><div className="mobile-brand">Prospect Sites</div><button className="theme-toggle" onClick={() => setTheme(theme === "light" ? "dark" : "light")} title={theme === "light" ? "Ativar modo escuro" : "Ativar modo claro"}>{theme === "light" ? <Moon size={17}/> : <Sun size={17}/>}<span>{theme === "light" ? "Escuro" : "Claro"}</span></button></header>

      {activeView === "prospecting" && <>
      <section className="metrics-row">
        <article><span><Users size={18}/></span><div><strong>{stats.active ?? leads.filter((lead) => !lead.archived).length}</strong><small>Leads qualificados</small></div></article>
        <article><span><MessageCircle size={18}/></span><div><strong>{stats.sent || 0}</strong><small>Mensagens enviadas</small></div></article>
        <article><span><CalendarDays size={18}/></span><div><strong>{stats.sent_today || 0}</strong><small>Mensagens enviadas hoje</small></div></article>
        <article><span><ArchiveRestore size={18}/></span><div><strong>{stats.archived || 0}</strong><small>Leads arquivados</small></div></article>
      </section>

      <section className="search-card">
        <div className="panel-title"><span><Search size={19}/></span><div><h1>Nova pesquisa</h1><p>Encontre empresas sem site próprio usando o limite de avaliações que você escolher.</p></div></div>
        <div className="mode-tabs">
          <button className={mode === "free" ? "active" : ""} onClick={() => setMode("free")}>Pesquisa livre</button>
          <button className={mode === "catalog" ? "active" : ""} onClick={() => setMode("catalog")}>Explorar nichos</button>
        </div>

        <form onSubmit={search}>
          {mode === "free" ? (
            <div className="free-search">
              <label><span>Palavra-chave completa</span><div className="input-shell"><Building2 size={17}/><input required value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ex: Clínica odontológica Asa Norte Brasília"/></div></label>
              <label className="reviews-field"><span>Mais de quantas avaliações?</span><div className="input-shell"><Star size={16}/><input type="number" min="0" max="100000" value={minimumReviews} onChange={(event) => setMinimumReviews(event.target.value)} /></div></label>
              <button className="primary" disabled={busy}><Radar size={17}/>{busy ? "Pesquisando..." : "Pesquisar"}</button>
            </div>
          ) : (
            <div className="catalog-search">
              <div className="cascade-grid">
                <label><span>Segmento</span><select value={category} onChange={(event) => { setCategory(event.target.value); setSelectedNiche(""); }}><option value="">Selecione um segmento</option>{Object.keys(NICHE_CATEGORIES).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
                <label><span>Nicho</span><select value={selectedNiche} onChange={(event) => setSelectedNiche(event.target.value)} disabled={!category}><option value="">{category ? "Selecione um nicho" : "Escolha o segmento primeiro"}</option>{category && NICHE_CATEGORIES[category].map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
                <label><span>Cidade, bairro ou região</span><div className="input-shell"><MapPin size={17}/><input required value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Ex: Asa Norte Brasília"/></div></label>
                <label><span>Mais de quantas avaliações?</span><div className="input-shell"><Star size={16}/><input type="number" min="0" max="100000" value={minimumReviews} onChange={(event) => setMinimumReviews(event.target.value)} /></div></label>
                <button className="primary" disabled={busy || !selectedNiche || !location}><Radar size={17}/>{busy ? "Pesquisando..." : "Pesquisar nicho"}</button>
              </div>
            </div>
          )}
        </form>
      </section>

      {job && <div className={`job ${job.status}`}><LoaderCircle className={busy ? "spin" : ""} size={18}/><div><strong>{job.status === "completed" ? "Concluído" : job.status === "failed" ? "Atenção" : "Analisando perfis"}</strong><span>{job.detail || "Preparando pesquisa..."}</span></div></div>}
      {notice && <div className="notice">{notice}</div>}

      <section className="workspace">
        <div className="leads-panel">
          <div className="panel-head">
            <div className="panel-title"><span><Users size={19}/></span><div><h2>Leads encontrados</h2><p>Fila com até 100 contatos pendentes por vez.</p></div></div>
            <div className="panel-controls"><div className="filters"><button className={dateFilter === "all" ? "active" : ""} onClick={() => setDateFilter("all")}>Todos</button><button className={dateFilter === "today" ? "active" : ""} onClick={() => setDateFilter("today")}><CalendarDays size={13}/>Hoje</button></div><button className="archive-today" onClick={() => loadLeads({ refreshStats: true })} title="Carregar a fila atual de leads pendentes"><RotateCcw size={14}/>Atualizar fila</button><button className="archive-today" onClick={archiveSent} disabled={!sentCount} title="Mover enviados para a lista mínima de bloqueio"><Check size={14}/>Arquivar enviados</button></div>
          </div>
          <div className="table-wrap">
            <table><thead><tr><th>Posição</th><th>Empresa</th><th>Avaliações</th><th>Site atual</th><th>Contato Google</th><th>Status</th><th>Ações</th></tr></thead>
              <tbody>{visible.map((lead, index) => <tr key={lead.place_id} className={`${lead.sent ? "sent-row" : ""} ${lead.archived ? "archived-row" : ""}`}>
                <td><span className="rank">{index + 1}º</span></td>
                <td><strong>{lead.company_name}</strong><small>{lead.date}</small></td>
                <td><span className="rating"><Star size={13}/>{Number(lead.rating || 0).toFixed(1)} <b>({lead.review_count})</b></span></td>
                <td>{lead.current_site ? <a className="platform-tag" href={lead.current_site} target="_blank" rel="noreferrer">{lead.site_platform}<ExternalLink size={11}/></a> : <span className="platform-tag no-site">Sem site</span>}</td>
                <td>{lead.phone || <span className="muted">Não informado</span>}</td>
                <td><button className={`status-toggle ${lead.sent ? "sent-badge" : "pending-badge"}`} disabled={Boolean(leadActions[lead.place_id])} onClick={() => changeSentStatus(lead, !lead.sent)} title={lead.sent ? "Alterar manualmente para pendente" : "Alterar manualmente para enviado"}>{leadActions[lead.place_id] === "status" ? <LoaderCircle className="spin" size={12}/> : lead.sent ? <><Check size={12}/>Enviado</> : <>Pendente</>}</button>{lead.sent_at && <small>{lead.sent_at}</small>}</td>
                <td><div className="row-actions">{lead.maps_link && <a className="icon-action" href={lead.maps_link} target="_blank" rel="noreferrer" title="Google Maps"><MapPinned size={15}/></a>}{lead.whatsapp_link ? <a className="whatsapp-action" href={whatsappHref(lead)} onClick={(event) => openLeadContact(event, lead, whatsappHref(lead))}><MessageCircle size={15}/>{leadActions[lead.place_id] === "sending" ? "Salvando..." : "Abrir WhatsApp"}</a> : lead.site_platform === "Instagram" && lead.current_site ? <a className="instagram-action" href={lead.current_site} onClick={(event) => openLeadContact(event, lead, lead.current_site)}><Instagram size={15}/>{leadActions[lead.place_id] === "sending" ? "Salvando..." : "Abrir Instagram"}</a> : <span className="no-whatsapp">Sem contato</span>}{!lead.archived && <button className="delete-action" disabled={Boolean(leadActions[lead.place_id])} onClick={() => deleteLead(lead)} title="Excluir do painel">{leadActions[lead.place_id] === "archiving" ? <LoaderCircle className="spin" size={15}/> : <Trash2 size={15}/>}</button>}</div></td>
              </tr>)}</tbody>
            </table>
            {!loading && !visible.length && <div className="empty"><Radar size={31}/><strong>Nenhum lead qualificado</strong><span>Faça uma pesquisa para alimentar sua base.</span></div>}
          </div>
        </div>

      </section>
      </>}

      {activeView === "leads" && <section className="history-page">
        <div className="history-hero">
          <div className="panel-title"><span><Users size={19}/></span><div><h1>Base de leads</h1><p>Histórico organizado de todas as empresas salvas no banco de dados.</p></div></div>
          <span className="history-count">Página {historyPage + 1} · até 20 leads</span>
        </div>
        <form className="history-filters" onSubmit={(event) => { event.preventDefault(); setHistoryPage(0); setHistoryCursors([null]); loadHistory({ cursor: null }); }}>
          <label className="history-search"><span>Pesquisar empresa</span><div className="input-shell"><Search size={17}/><input value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder="Digite o nome da empresa" /></div></label>
          <label><span>Data inicial</span><input type="date" value={historyStartDate} onChange={(event) => { setHistoryPeriod("custom"); setHistoryStartDate(event.target.value); }} /></label>
          <label><span>Data final</span><input type="date" value={historyEndDate} onChange={(event) => { setHistoryPeriod("custom"); setHistoryEndDate(event.target.value); }} /></label>
          <button className="primary" type="submit" disabled={historyLoading}><ListFilter size={17}/>{historyLoading ? "Filtrando..." : "Aplicar filtros"}</button>
        </form>
        <div className="history-periods" aria-label="Filtros rápidos por período"><span>Período rápido:</span><button className={historyPeriod === "15" ? "active" : ""} onClick={() => applyHistoryPeriod("15")}>Últimos 15 dias</button><button className={historyPeriod === "30" ? "active" : ""} onClick={() => applyHistoryPeriod("30")}>Últimos 30 dias</button><button className={historyPeriod === "all" ? "active" : ""} onClick={() => applyHistoryPeriod("all")}>Todo o histórico</button></div>
        <div className="leads-panel history-table-panel">
          <div className="table-wrap">
            <table className="history-table"><thead><tr><th>Coletado em</th><th>Empresa</th><th>Contato</th><th>Avaliações</th><th>Localização</th><th>Site atual</th><th>Mensagem</th><th>Arquivamento</th></tr></thead>
              <tbody>{historyLeads.map((lead) => <tr key={lead.place_id} className={lead.sent ? "sent-row" : ""}>
                <td><strong>{lead.date}</strong>{lead.sent_at && <small>Enviado: {lead.sent_at}</small>}</td>
                <td><strong>{lead.company_name}</strong></td>
                <td>{lead.phone || <span className="muted">Não informado</span>}</td>
                <td><span className="rating"><Star size={13}/>{Number(lead.rating || 0).toFixed(1)} <b>({lead.review_count})</b></span></td>
                <td>{[lead.city, lead.state].filter(Boolean).join(" · ") || lead.address || <span className="muted">Não informado</span>}</td>
                <td>{lead.current_site ? <a className="platform-tag" href={lead.current_site} target="_blank" rel="noreferrer">{lead.site_platform || "Abrir site"}<ExternalLink size={11}/></a> : <span className="platform-tag no-site">Sem site</span>}</td>
                <td><span className={lead.sent ? "sent-badge" : "pending-badge"}>{lead.sent ? <><Check size={12}/>Enviada</> : "Pendente"}</span></td>
                <td>{lead.archived ? <span className="archived-badge">Arquivado</span> : <span className="active-badge">Ativo</span>}</td>
              </tr>)}</tbody>
            </table>
            {!historyLoading && !historyLeads.length && <div className="empty"><Users size={31}/><strong>Nenhum lead encontrado</strong><span>Altere a busca ou o período selecionado.</span></div>}
          </div>
          <div className="pagination"><button disabled={historyLoading || historyPage === 0} onClick={() => changeHistoryPage("previous")}>Anterior</button><span>Página {historyPage + 1}</span><button disabled={historyLoading || !historyNextCursor} onClick={() => changeHistoryPage("next")}>Próxima</button></div>
        </div>
      </section>}

      {activeView === "settings" && <section className="settings-page">
        <div className="history-hero"><div className="panel-title"><span><Settings size={19}/></span><div><h1>Configurações de API</h1><p>Cadastre chaves autorizadas e escolha qual API do Google Maps será usada nas pesquisas.</p></div></div></div>
        {settingsNotice && <div className={`settings-notice ${settingsNotice.includes("sucesso") || settingsNotice.includes("ativa agora") ? "success" : "error"}`}>{settingsNotice}</div>}
        <div className="settings-grid"><form className="settings-card" onSubmit={saveApiKey}><div className="panel-title"><span><KeyRound size={18}/></span><div><h2>Nova API</h2><p>A chave é enviada com segurança ao backend e nunca é exibida novamente.</p></div></div><label><span>Nome para identificar a API</span><input value={apiName} onChange={(event) => setApiName(event.target.value)} placeholder="Ex: API Vinícius" required /></label><label><span>Chave da API do Google Maps</span><input type="password" value={apiValue} onChange={(event) => setApiValue(event.target.value)} placeholder="Cole a chave aqui" required autoComplete="off" /></label><button className="primary" disabled={settingsLoading}><KeyRound size={17}/>{settingsLoading ? "Salvando..." : "Salvar e usar esta API"}</button></form><div className="settings-card api-status-card"><div className="panel-title"><span><AlertTriangle size={18}/></span><div><h2>Status das APIs</h2><p>Uma chave marcada como esgotada precisa ser ativada novamente manualmente após a renovação.</p></div></div><div className="api-key-list">{apiKeys.map((key) => <article key={key.id}><div><strong>{key.name}</strong><small>{key.status === "active" ? "Em uso" : key.status === "exhausted" ? `Limite atingido · renovação estimada: ${key.renews_on || "consulte o Google Cloud"}` : "Disponível"}</small>{key.last_error && <small className="api-error">{key.last_error}</small>}</div><div>{key.status === "active" ? <span className="active-badge">Ativa</span> : <button className="activate-api" disabled={settingsLoading} onClick={() => activateApiKey(key)}>Usar esta API</button>}</div></article>)}{!settingsLoading && !apiKeys.length && <div className="empty"><KeyRound size={28}/><strong>Nenhuma API cadastrada</strong><span>Cadastre uma chave para gerenciá-la por aqui.</span></div>}</div></div></div>
      </section>}

      {activeView === "history" && <section className="history-page"><div className="history-hero"><div className="panel-title"><span><History size={19}/></span><div><h1>Histórico de exclusões</h1><p>Leads excluídos manualmente do painel. Você pode restaurá-los a qualquer momento.</p></div></div><span className="history-count">{deletedLeads.filter((lead) => !lead.restored_at).length} excluído(s)</span></div><div className="leads-panel history-table-panel"><div className="table-wrap"><table><thead><tr><th>Empresa</th><th>Contato</th><th>Coletado em</th><th>Excluído em</th><th>Situação</th><th>Ação</th></tr></thead><tbody>{deletedLeads.map((lead) => <tr key={lead.place_id}><td><strong>{lead.company_name}</strong></td><td>{lead.phone || <span className="muted">Não informado</span>}</td><td>{lead.date || "—"}</td><td>{lead.deleted_at ? new Date(lead.deleted_at).toLocaleString("pt-BR") : "—"}</td><td>{lead.restored_at ? <span className="active-badge">Restaurado</span> : <span className="archived-badge">Excluído</span>}</td><td>{lead.restored_at ? <span className="muted">Já está na base</span> : <button className="activate-api" onClick={() => restoreLead(lead)}><Undo2 size={14}/>Restaurar</button>}</td></tr>)}</tbody></table>{!deletionHistoryLoading && !deletedLeads.length && <div className="empty"><History size={30}/><strong>Nenhuma exclusão registrada</strong><span>Quando você excluir um lead individualmente, ele aparecerá aqui.</span></div>}</div></div></section>}

      {messageOpen && <div className="message-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setMessageOpen(false); }}>
        <aside className="message-modal" role="dialog" aria-modal="true" aria-label="Configuração da mensagem">
          <button className="modal-close" onClick={() => setMessageOpen(false)} title="Fechar"><X size={19}/></button>
          <div className="panel-title"><span><MessageCircle size={19}/></span><div><h2>Mensagem</h2><p>Texto preenchido no WhatsApp.</p></div></div>
          <label className="message-label"><span>Mensagem de abordagem</span><textarea value={messageDraft} onChange={(event) => setMessageDraft(event.target.value)} maxLength="3000"/><small className="template-tip">Variáveis: <b>[Empresa]</b>, <b>[AVALIAÇÕES]</b> e <b>[NOTA]</b>.</small></label>
          <div className="message-save-row"><span>{messageDraft === message ? "Mensagem salva" : "Alterações ainda não salvas"}</span><button onClick={saveMessage} disabled={messageSaving || !messageDraft.trim() || messageDraft === message}><Check size={15}/>{messageSaving ? "Salvando..." : "Salvar mensagem"}</button></div>
          {sendMode === "manual" ? <div className="manual-note"><MessageCircle size={16}/><p>Use o botão “Abrir WhatsApp” de cada lead. A mensagem será preenchida e o envio continuará sob sua confirmação.</p></div> : <div className="dispatch-box">
            <div className="dispatch-grid">
              <label><span>Quantidade nesta sessão</span><input type="number" min="1" max="500" value={sessionAmount} onChange={(event) => setSessionAmount(event.target.value)}/></label>
              <label><span>Mensagens por lote</span><input type="number" min="1" max="100" value={batchSize} onChange={(event) => setBatchSize(event.target.value)}/></label>
              <label><span>Intervalo mínimo</span><div className="number-unit"><input type="number" min="0" max="1440" value={messageIntervalMin} onChange={(event) => setMessageIntervalMin(event.target.value)}/><small>min</small></div></label>
              <label><span>Intervalo máximo</span><div className="number-unit"><input type="number" min="0" max="1440" value={messageIntervalMax} onChange={(event) => setMessageIntervalMax(event.target.value)}/><small>min</small></div></label>
              <label><span>Pausa entre lotes</span><div className="number-unit"><input type="number" min="0" max="1440" value={batchPause} onChange={(event) => setBatchPause(event.target.value)}/><small>min</small></div></label>
            </div>
            {!dispatch && <button className="dispatch-primary" onClick={startDispatch}><Play size={16}/>Iniciar no WhatsApp Desktop</button>}
            {dispatch && <div className="dispatch-status">
              <div className="dispatch-progress"><span>Progresso</span><strong>{Math.min(dispatch.index, dispatch.queue.length)}/{dispatch.queue.length}</strong></div>
              {dispatch.status === "completed" ? <div className="session-complete"><Check size={17}/>Sessão concluída</div> : <>
                <div className="next-lead"><small>Próximo lead</small><strong>{dispatch.queue[dispatch.index]?.company_name}</strong></div>
                {dispatch.status === "waiting" && !dispatchReady && <div className="countdown"><Clock size={17}/><div><small>{dispatch.waitingType === "batch" ? "Pausa do lote" : "Próxima mensagem"}</small><strong>{countdownLabel}</strong></div></div>}
                {dispatch.status === "paused" && <div className="countdown"><Pause size={17}/><div><small>Sessão pausada</small><strong>{`${String(Math.floor((dispatch.pausedRemaining || 0) / 60)).padStart(2, "0")}:${String((dispatch.pausedRemaining || 0) % 60).padStart(2, "0")}`}</strong></div></div>}
                <div className="dispatch-actions">
                  {dispatch.status === "paused" ? <button onClick={() => { const seconds = dispatch.pausedRemaining || 0; setClock(Date.now()); setDispatch({ ...dispatch, status: "waiting", nextAt: Date.now() + seconds * 1000 }); }}><Play size={14}/>Retomar</button> : <button onClick={() => setDispatch({ ...dispatch, status: "paused", pausedRemaining: remainingSeconds })}><Pause size={14}/>Pausar</button>}
                  <button onClick={() => setDispatch(null)}><RotateCcw size={14}/>Encerrar</button>
                </div>
              </>}
              {dispatch.status === "completed" && <button className="dispatch-secondary" onClick={() => setDispatch(null)}><RotateCcw size={14}/>Nova sessão</button>}
            </div>}
            <div className="manual-note"><Clock size={16}/><p>Inicie uma vez e permaneça no WhatsApp Desktop. Ao terminar cada intervalo, o aplicativo receberá o próximo contato com a mensagem preenchida.</p></div>
          </div>}
        </aside>
      </div>}
      {activeView === "settings" && apiKeys.length > 0 && <section className="api-usage-section"><h2>Uso estimado no Prospect Sites</h2><p>Contagem das requisições feitas por este sistema neste mês. Chamadas feitas fora daqui não entram neste cálculo.</p><div className="api-usage-list">{apiKeys.map((key) => <article key={key.id}><div><strong>{key.name}</strong><small>{key.status === "active" ? "Em uso" : key.status === "exhausted" ? "Franquia mensal esgotada" : "Disponível"}</small></div><div className="api-usage-numbers"><b>{key.requests_used || 0} / {key.monthly_request_limit || 1000}</b><span>{key.requests_remaining ?? 1000} restantes</span><small>Renova em {formatDate(key.next_renewal_on)}</small></div><button className="delete-api" disabled={settingsLoading} onClick={() => deleteApiKey(key)} title={`Excluir ${key.name}`}><Trash2 size={14}/>Excluir</button></article>)}</div></section>}
      </div></main>
  );
}

createRoot(document.getElementById("root")).render(<App/>);
