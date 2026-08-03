import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Archive, ArchiveRestore, Building2, CalendarDays, Check, ExternalLink, Instagram, LoaderCircle, MapPin,
  Clock, KeyRound, Lock, LogOut, Mail, MapPinned, MessageCircle, Moon, Pause, Play, Radar, RotateCcw,
  Search, Star, Sun, Trash2, Users
} from "lucide-react";
import { NICHE_CATEGORIES } from "./niches";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const LEADS_CACHE = "prospect-leads-cache";
const STATS_CACHE = "prospect-stats-cache";
const MESSAGE_CACHE = "prospect-message-template";
const AUTH_TOKEN = "prospect-auth-token";
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
  const token = localStorage.getItem(AUTH_TOKEN);
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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

function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const session = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      localStorage.setItem(AUTH_TOKEN, session.access_token);
      onLogin(email);
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setSubmitting(false);
    }
  };

  return <main className="login-page"><section className="login-card">
    <div className="login-brand"><span><Radar size={23}/></span><div><strong>Prospect Sites</strong><small>Acesso administrativo</small></div></div>
    <div className="login-copy"><span><Lock size={18}/></span><h1>Entre no seu painel</h1><p>Use suas credenciais para acessar os leads e pesquisas.</p></div>
    <form onSubmit={submit} className="login-form">
      <label><span>E-mail</span><div className="input-shell"><Mail size={17}/><input type="email" required autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="seu@email.com"/></div></label>
      <label><span>Senha</span><div className="input-shell"><KeyRound size={17}/><input type="password" required minLength="8" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Sua senha"/></div></label>
      {error && <div className="login-error">{error}</div>}
      <button className="primary" disabled={submitting}>{submitting ? <LoaderCircle className="spin" size={17}/> : <Lock size={17}/>} {submitting ? "Entrando..." : "Entrar"}</button>
    </form>
  </section></main>;
}

function App() {
  const [authStatus, setAuthStatus] = useState("checking");
  const [authEmail, setAuthEmail] = useState("");
  const [leads, setLeads] = useState(() => readCache(LEADS_CACHE, []));
  const [mode, setMode] = useState("free");
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
  const dispatchWindowRef = useRef(null);

  const loadLeads = async ({ silent = false, retries = 5 } = {}) => {
    let lastError;
    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        const leadItems = await api("/api/leads");
        setLeads(leadItems);
        localStorage.setItem(LEADS_CACHE, JSON.stringify(leadItems));
        try {
          const metrics = await api("/api/stats");
          setStats(metrics);
          localStorage.setItem(STATS_CACHE, JSON.stringify(metrics));
        } catch {
          // Os leads já foram atualizados; a métrica será renovada na próxima tentativa.
        }
        setNotice("");
        setLoading(false);
        return;
      } catch (error) {
        lastError = error;
        if (attempt < retries) await wait(Math.min(2000 + attempt * 1500, 8000));
      }
    }
    if (!silent) setNotice(lastError?.message || "Não foi possível atualizar os leads.");
    setLoading(false);
  };

  useEffect(() => {
    const token = localStorage.getItem(AUTH_TOKEN);
    if (!token) {
      setAuthStatus("guest");
      return;
    }
    api("/api/auth/me")
      .then((account) => {
        setAuthEmail(account.email);
        setAuthStatus("authenticated");
      })
      .catch(() => {
        localStorage.removeItem(AUTH_TOKEN);
        setAuthStatus("guest");
      });
  }, []);

  useEffect(() => {
    if (authStatus === "authenticated") {
      loadLeads({ silent: leads.length > 0 });
    }
  }, [authStatus]);

  useEffect(() => {
    localStorage.setItem(LEADS_CACHE, JSON.stringify(leads));
  }, [leads]);

  useEffect(() => {
    localStorage.setItem(STATS_CACHE, JSON.stringify(stats));
  }, [stats]);

  useEffect(() => {
    localStorage.setItem(MESSAGE_CACHE, message);
  }, [message]);

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
        if (current.status === "completed") loadLeads();
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
      .filter((lead) => dateFilter === "all" || lead.date === today)
      .sort((a, b) =>
        Number(a.sent) - Number(b.sent)
        || Number(b.review_count || 0) - Number(a.review_count || 0)
        || Number(b.rating || 0) - Number(a.rating || 0)
        || a.company_name.localeCompare(b.company_name, "pt-BR")
      ),
    [leads, dateFilter, today]
  );
  const sentCount = leads.filter((lead) => lead.sent).length;
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

  const markSent = async (placeId) => {
    const previous = leads;
    const previousStats = stats;
    const wasSent = leads.some((lead) => lead.place_id === placeId && lead.sent);
    setLeads((items) => items.map((lead) =>
      lead.place_id === placeId ? { ...lead, sent: true } : lead
    ));
    if (!wasSent) {
      setStats((current) => ({
        ...current,
        sent: Number(current.sent || 0) + 1,
        sent_today: Number(current.sent_today || 0) + 1,
      }));
    }
    try {
      const updated = await api(`/api/leads/${encodeURIComponent(placeId)}/sent`, { method: "POST" });
      setLeads((items) => items.map((lead) => lead.place_id === placeId ? updated : lead));
    } catch (error) {
      setLeads(previous);
      setStats(previousStats);
      setNotice(`O WhatsApp foi aberto, mas não foi possível marcar como enviado: ${error.message}`);
    }
  };

  const deleteLead = async (lead) => {
    if (!window.confirm(`Arquivar ${lead.company_name}? Ele sairá do painel, mas continuará salvo no histórico.`)) return;
    const previous = leads;
    setLeads((items) => items.filter((item) => item.place_id !== lead.place_id));
    try {
      await api(`/api/leads/${encodeURIComponent(lead.place_id)}`, { method: "DELETE" });
      await loadLeads();
    } catch (error) {
      setLeads(previous);
      setNotice(`Não foi possível arquivar o lead: ${error.message}`);
    }
  };

  const archiveToday = async () => {
    const todayLeads = leads.filter((lead) => lead.date === today);
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
    const sentLeads = leads.filter((lead) => lead.sent);
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

  const logout = () => {
    localStorage.removeItem(AUTH_TOKEN);
    localStorage.removeItem(LEADS_CACHE);
    localStorage.removeItem(STATS_CACHE);
    setLeads([]);
    setStats({ archived: 0 });
    setAuthEmail("");
    setAuthStatus("guest");
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

  const advanceDispatch = (session = dispatch, targetWindow = dispatchWindowRef.current) => {
    if (!session || session.index >= session.queue.length) return;
    if (!targetWindow || targetWindow.closed) {
      setNotice("A janela do WhatsApp Web foi fechada. Inicie uma nova sessão.");
      setDispatch({ ...session, status: "paused", pausedRemaining: 0 });
      return;
    }
    const lead = session.queue[session.index];
    targetWindow.location.href = whatsappHref(lead);
    markSent(lead.place_id);
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

  if (authStatus === "checking") {
    return <main className="auth-loading"><LoaderCircle className="spin" size={28}/><span>Verificando acesso...</span></main>;
  }

  if (authStatus !== "authenticated") {
    return <LoginScreen onLogin={(email) => { setAuthEmail(email); setAuthStatus("authenticated"); }}/>
  }

  return (
    <main>
      <header className="topbar"><a className="brand" href="#"><span><Radar size={20}/></span>Prospect Sites</a><div className="header-actions"><small>{authEmail}</small><button className="theme-toggle" onClick={() => setTheme(theme === "light" ? "dark" : "light")} title={theme === "light" ? "Ativar modo escuro" : "Ativar modo claro"}>{theme === "light" ? <Moon size={17}/> : <Sun size={17}/>}<span>{theme === "light" ? "Escuro" : "Claro"}</span></button><button className="logout-button" onClick={logout} title="Sair"><LogOut size={17}/><span>Sair</span></button></div></header>

      <section className="metrics-row">
        <article><span><Users size={18}/></span><div><strong>{leads.length}</strong><small>Leads qualificados</small></div></article>
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
            <div className="panel-title"><span><Users size={19}/></span><div><h2>Leads encontrados</h2><p>Contatos qualificados para abordagem individual.</p></div></div>
            <div className="panel-controls"><div className="filters"><button className={dateFilter === "all" ? "active" : ""} onClick={() => setDateFilter("all")}>Todos</button><button className={dateFilter === "today" ? "active" : ""} onClick={() => setDateFilter("today")}><CalendarDays size={13}/>Hoje</button></div><button className="archive-today" onClick={archiveSent} disabled={!sentCount} title="Retirar enviados do painel sem apagar da planilha"><Check size={14}/>Arquivar enviados</button><button className="archive-today" onClick={archiveToday} title="Retirar do painel sem apagar da planilha"><Archive size={14}/>Arquivar leads de hoje</button></div>
          </div>
          <div className="table-wrap">
            <table><thead><tr><th>Posição</th><th>Empresa</th><th>Avaliações</th><th>Site atual</th><th>Contato</th><th>Status</th><th>Ações</th></tr></thead>
              <tbody>{visible.map((lead, index) => <tr key={lead.place_id} className={lead.sent ? "sent-row" : ""}>
                <td><span className="rank">{index + 1}º</span></td>
                <td><strong>{lead.company_name}</strong><small>{lead.date}</small></td>
                <td><span className="rating"><Star size={13}/>{Number(lead.rating || 0).toFixed(1)} <b>({lead.review_count})</b></span></td>
                <td>{lead.current_site ? <a className="platform-tag" href={lead.current_site} target="_blank" rel="noreferrer">{lead.site_platform}<ExternalLink size={11}/></a> : <span className="platform-tag no-site">Sem site</span>}</td>
                <td>{lead.phone || <span className="muted">Não informado</span>}</td>
                <td>{lead.sent ? <span className="sent-badge"><Check size={12}/>Enviado</span> : <span className="pending-badge">Pendente</span>}{lead.sent_at && <small>{lead.sent_at}</small>}</td>
                <td><div className="row-actions">{lead.maps_link && <a className="icon-action" href={lead.maps_link} target="_blank" rel="noreferrer" title="Google Maps"><MapPinned size={15}/></a>}{lead.whatsapp_link ? <a className={`whatsapp-action ${lead.sent ? "sent" : ""}`} href={whatsappHref(lead)} onClick={() => markSent(lead.place_id)}><MessageCircle size={15}/>{lead.sent ? "Abrir novamente" : "Abrir WhatsApp"}</a> : lead.site_platform === "Instagram" && lead.current_site ? <a className={`instagram-action ${lead.sent ? "sent" : ""}`} href={lead.current_site} target="_blank" rel="noreferrer" onClick={() => markSent(lead.place_id)}><Instagram size={15}/>{lead.sent ? "Abrir novamente" : "Abrir Instagram"}</a> : <span className="no-whatsapp">Sem contato</span>}<button className="delete-action" onClick={() => deleteLead(lead)} title="Arquivar lead"><Trash2 size={15}/></button></div></td>
              </tr>)}</tbody>
            </table>
            {!loading && !visible.length && <div className="empty"><Radar size={31}/><strong>Nenhum lead qualificado</strong><span>Faça uma pesquisa para alimentar sua base.</span></div>}
          </div>
        </div>

        <aside>
          <div className="panel-title"><span><MessageCircle size={19}/></span><div><h2>Mensagem</h2><p>Texto preenchido no WhatsApp.</p></div></div>
          <div className="send-mode"><button className={sendMode === "manual" ? "active" : ""} onClick={() => setSendMode("manual")}>Manual</button><button className={sendMode === "assisted" ? "active" : ""} onClick={() => setSendMode("assisted")}>Sessão assistida</button></div>
          <label className="message-label"><span>Mensagem de abordagem</span><textarea value={message} onChange={(event) => setMessage(event.target.value)} maxLength="3000"/><small className="template-tip">Salva automaticamente. Variáveis: <b>[Empresa]</b>, <b>[AVALIAÇÕES]</b> e <b>[NOTA]</b>.</small></label>
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
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App/>);
