import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Building2, CalendarDays, CheckCircle2, ExternalLink, LoaderCircle,
  MessageCircle, Radar, Search, Send, Sparkles, Users
} from "lucide-react";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function errorMessage(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || "Dados inválidos")
      .join(" · ");
  }
  return detail?.message || "Não foi possível concluir.";
}

async function api(path, options) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    throw new ApiError(errorMessage(body.detail), response.status);
  }
  return body;
}

function App() {
  const [leads, setLeads] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [message, setMessage] = useState(
    "Olá! Vi sua empresa no Google e preparei uma ideia para melhorar sua presença online. Posso te mostrar?"
  );
  const [delay, setDelay] = useState(30);
  const [job, setJob] = useState(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const loadLeads = async () => {
    try {
      setLeads(await api("/api/leads"));
    } catch (error) {
      setNotice(error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadLeads(); }, []);

  useEffect(() => {
    if (!job || ["completed", "failed"].includes(job.status)) return;
    const timer = setInterval(async () => {
      try {
        const current = await api(`/api/jobs/${job.id}`);
        setJob(current);
        if (current.status === "completed") loadLeads();
      } catch (error) {
        setNotice(error.message);
        setJob((current) => current ? {
          ...current,
          status: "failed",
          detail: error.status === 404
            ? "A tarefa foi interrompida porque o servidor reiniciou."
            : error.message,
        } : current);
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [job?.id, job?.status]);

  const today = new Intl.DateTimeFormat("pt-BR").format(new Date());
  const visible = useMemo(
    () => leads.filter((lead) => filter === "all" || lead.date === today),
    [leads, filter, today]
  );

  const toggle = (id) => setSelected((current) => {
    const next = new Set(current);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const search = async (event) => {
    event.preventDefault();
    setNotice("");
    try {
      setJob(await api("/api/search", {
        method: "POST",
        body: JSON.stringify({ query }),
      }));
    } catch (error) { setNotice(error.message); }
  };

  const send = async () => {
    if (!selected.size) return setNotice("Selecione pelo menos um lead.");
    if (!window.confirm(`Confirmar o envio para ${selected.size} contato(s)?`)) return;
    setNotice("");
    try {
      setJob(await api("/api/send", {
        method: "POST",
        body: JSON.stringify({
          place_ids: [...selected],
          message,
          delay_seconds: Number(delay),
          confirmed: true,
        }),
      }));
    } catch (error) { setNotice(error.message); }
  };

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#"><span><Radar size={20}/></span>Prospect Sites</a>
        <div className="status"><i/> Agente local conectado</div>
      </header>

      <section className="hero">
        <div>
          <div className="eyebrow"><Sparkles size={14}/> Inteligência comercial</div>
          <h1>Encontre oportunidades<br/><em>antes da concorrência.</em></h1>
          <p>Descubra anunciantes sem site profissional, organize seus leads e conduza sua prospecção em um só lugar.</p>
        </div>
        <div className="hero-stat">
          <span>Leads na base</span>
          <strong>{leads.length}</strong>
          <small><Users size={14}/> atualizados via Google Sheets</small>
        </div>
      </section>

      <section className="search-card">
        <div className="section-title"><span><Search size={20}/></span><div><h2>Nova pesquisa</h2><p>Digite livremente o nicho, bairro, cidade ou distrito que deseja mapear.</p></div></div>
        <form onSubmit={search}>
          <label><span>Palavra-chave completa</span><div><Building2 size={18}/><input required minLength="2" maxLength="200" value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Ex: Clínica odontológica Asa Sul Brasília"/></div></label>
          <button className="primary" disabled={job && !["completed","failed"].includes(job.status)}><Radar size={18}/> Iniciar pesquisa</button>
        </form>
      </section>

      {job && <div className={`job ${job.status}`}>
        <LoaderCircle className={["queued","running"].includes(job.status) ? "spin" : ""} size={18}/>
        <div><strong>{job.status === "completed" ? "Concluído" : job.status === "failed" ? "Atenção" : "Processando"}</strong><span>{job.detail || "Preparando tarefa..."}</span></div>
        {job.total > 0 && <b>{job.processed}/{job.total}</b>}
      </div>}
      {notice && <div className="notice">{notice}</div>}

      <section className="workspace">
        <div className="leads-panel">
          <div className="panel-head">
            <div className="section-title"><span><Users size={20}/></span><div><h2>Leads encontrados</h2><p>Selecione os contatos que deseja abordar.</p></div></div>
            <div className="filters">
              <button className={filter==="all"?"active":""} onClick={()=>setFilter("all")}>Todos</button>
              <button className={filter==="today"?"active":""} onClick={()=>setFilter("today")}><CalendarDays size={14}/> Hoje</button>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th></th><th>Empresa</th><th>Contato</th><th>Site atual</th><th>Data</th></tr></thead>
              <tbody>
                {visible.map((lead) => <tr key={lead.place_id}>
                  <td><input type="checkbox" checked={selected.has(lead.place_id)} onChange={()=>toggle(lead.place_id)}/></td>
                  <td><strong>{lead.company_name}</strong><small>{lead.place_id}</small></td>
                  <td>{lead.phone || "Não informado"}{lead.whatsapp_link && <a href={lead.whatsapp_link} target="_blank"><MessageCircle size={14}/></a>}</td>
                  <td>{lead.current_site ? <a href={lead.current_site} target="_blank">Abrir <ExternalLink size={13}/></a> : <span className="tag">Sem site</span>}</td>
                  <td>{lead.date}</td>
                </tr>)}
              </tbody>
            </table>
            {!loading && !visible.length && <div className="empty"><Radar size={34}/><strong>Nenhum lead por aqui</strong><span>Inicie uma pesquisa para alimentar sua base.</span></div>}
          </div>
        </div>

        <aside>
          <div className="section-title"><span><Send size={20}/></span><div><h2>Mensagem</h2><p>Personalize sua abordagem.</p></div></div>
          <label className="message-label"><span>Texto da prospecção</span><textarea value={message} onChange={(e)=>setMessage(e.target.value)} maxLength="2000"/></label>
          <div className="delay"><label><span>Intervalo entre envios</span><div><input type="number" min="10" max="3600" value={delay} onChange={(e)=>setDelay(e.target.value)}/><b>segundos</b></div></label></div>
          <div className="selection"><span><CheckCircle2 size={16}/>{selected.size} selecionado(s)</span><small>Revise os destinatários antes de confirmar.</small></div>
          <button className="send-button" onClick={send} disabled={!selected.size}><MessageCircle size={19}/> Disparar mensagens</button>
          <p className="legal">Envie apenas comunicações legítimas e respeite consentimento, opt-out e as políticas do WhatsApp.</p>
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
