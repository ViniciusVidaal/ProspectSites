import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Building2, CalendarDays, ExternalLink, LoaderCircle, MapPinned,
  MessageCircle, Radar, Search, Sparkles, Star, Users
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
    return detail.map((item) => item?.msg || "Dados inválidos").join(" · ");
  }
  return detail?.message || "Não foi possível concluir.";
}

async function api(path, options) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) throw new ApiError(errorMessage(body.detail), response.status);
  return body;
}

function App() {
  const [leads, setLeads] = useState([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [message, setMessage] = useState(
    "Olá! Encontrei sua empresa no Google e gostaria de apresentar uma ideia para melhorar sua presença online. Posso te mostrar?"
  );
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

  const search = async (event) => {
    event.preventDefault();
    setNotice("");
    try {
      setJob(await api("/api/search", {
        method: "POST",
        body: JSON.stringify({ query }),
      }));
    } catch (error) {
      setNotice(error.message);
    }
  };

  const whatsappHref = (lead) => {
    if (!lead.whatsapp_link) return "";
    const separator = lead.whatsapp_link.includes("?") ? "&" : "?";
    return `${lead.whatsapp_link}${separator}text=${encodeURIComponent(message.trim())}`;
  };

  const busy = job && !["completed", "failed"].includes(job.status);

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#"><span><Radar size={20}/></span>Prospect Sites</a>
        <div className="status"><i/> Google Places conectado</div>
      </header>

      <section className="hero">
        <div>
          <div className="eyebrow"><Sparkles size={14}/> Prospecção inteligente</div>
          <h1>Encontre negócios com<br/><em>presença digital limitada.</em></h1>
          <p>Mapeie perfis relevantes no Google com mais de 50 avaliações e presença baseada em redes sociais ou plataformas gratuitas.</p>
        </div>
        <div className="hero-stat">
          <span>Leads qualificados</span>
          <strong>{leads.length}</strong>
          <small><Users size={14}/> sincronizados via Google Sheets</small>
        </div>
      </section>

      <section className="search-card">
        <div className="section-title"><span><Search size={20}/></span><div><h2>Nova pesquisa</h2><p>Informe o nicho e a região na mesma palavra-chave.</p></div></div>
        <form onSubmit={search}>
          <label><span>Palavra-chave completa</span><div><Building2 size={18}/><input required minLength="2" maxLength="200" value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="Ex: Clínica odontológica Asa Norte Brasília"/></div></label>
          <button className="primary" disabled={busy}><Radar size={18}/> {busy ? "Pesquisando..." : "Iniciar pesquisa"}</button>
        </form>
        <p className="qualification-note">Filtro automático: mais de 50 avaliações + site cadastrado como Instagram, Facebook, LinkedIn, Linktree, WhatsApp ou plataforma semelhante.</p>
      </section>

      {job && <div className={`job ${job.status}`}>
        <LoaderCircle className={busy ? "spin" : ""} size={18}/>
        <div><strong>{job.status === "completed" ? "Concluído" : job.status === "failed" ? "Atenção" : "Analisando perfis"}</strong><span>{job.detail || "Preparando pesquisa..."}</span></div>
        {job.total > 0 && <b>{job.processed}/{job.total}</b>}
      </div>}
      {notice && <div className="notice">{notice}</div>}

      <section className="workspace">
        <div className="leads-panel">
          <div className="panel-head">
            <div className="section-title"><span><Users size={20}/></span><div><h2>Leads encontrados</h2><p>Empresas qualificadas prontas para abordagem individual.</p></div></div>
            <div className="filters">
              <button className={filter==="all"?"active":""} onClick={()=>setFilter("all")}>Todos</button>
              <button className={filter==="today"?"active":""} onClick={()=>setFilter("today")}><CalendarDays size={14}/> Hoje</button>
            </div>
          </div>
          <div className="table-wrap">
            <table className="lead-table">
              <thead><tr><th>Empresa</th><th>Avaliações</th><th>Plataforma</th><th>Contato</th><th>Ações</th></tr></thead>
              <tbody>
                {visible.map((lead) => <tr key={lead.place_id}>
                  <td><strong>{lead.company_name}</strong><small>{lead.date}</small></td>
                  <td><span className="rating"><Star size={13}/>{lead.rating?.toFixed?.(1) || lead.rating} <b>({lead.review_count})</b></span></td>
                  <td><a href={lead.current_site} target="_blank" rel="noreferrer" className="platform-tag">{lead.site_platform}<ExternalLink size={12}/></a></td>
                  <td>{lead.phone || <span className="muted">Não informado</span>}</td>
                  <td><div className="row-actions">
                    {lead.maps_link && <a href={lead.maps_link} target="_blank" rel="noreferrer" className="icon-action" title="Abrir no Google Maps"><MapPinned size={16}/></a>}
                    {lead.whatsapp_link ? <a href={whatsappHref(lead)} target="_blank" rel="noreferrer" className="whatsapp-action"><MessageCircle size={16}/> Abrir WhatsApp</a> : <span className="no-whatsapp">Sem WhatsApp</span>}
                  </div></td>
                </tr>)}
              </tbody>
            </table>
            {!loading && !visible.length && <div className="empty"><Radar size={34}/><strong>Nenhum lead qualificado</strong><span>Faça uma pesquisa para analisar os perfis do Google.</span></div>}
          </div>
        </div>

        <aside>
          <div className="section-title"><span><MessageCircle size={20}/></span><div><h2>Mensagem de abordagem</h2><p>Será preenchida no WhatsApp de cada lead.</p></div></div>
          <label className="message-label"><span>Texto da mensagem</span><textarea value={message} onChange={(event)=>setMessage(event.target.value)} maxLength="2000"/></label>
          <div className="manual-note"><MessageCircle size={17}/><div><strong>Envio individual e manual</strong><p>Clique em “Abrir WhatsApp” no lead desejado. Revise a mensagem e envie diretamente no WhatsApp.</p></div></div>
          <p className="legal">Respeite consentimento, opt-out e as políticas comerciais do WhatsApp.</p>
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
