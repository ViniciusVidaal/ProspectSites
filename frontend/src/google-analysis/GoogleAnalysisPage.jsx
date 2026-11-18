import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowLeft, BarChart3, Building2, CheckCircle2, ChevronRight,
  Clock3, Download, ExternalLink, FileSearch, FileText, Link2, LoaderCircle,
  MapPin, Play, RefreshCw, Search, ShieldCheck, Sparkles, Star, Target, XCircle, Coins
} from "lucide-react";
import { downloadGoogleAnalysisImage, formatMapPosition } from "./reportImage";
import "./google-analysis.css";


const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function neighborhoodFromAddress(address = "") {
  const matches = [...String(address).matchAll(/\s-\s([^,]+)(?=,)/g)]
    .map((match) => match[1].trim())
    .filter((value) => !/^[A-Z]{2}$/i.test(value));
  return matches.length ? matches.at(-1) : "";
}

function errorMessage(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg || "Dados inválidos").join(" · ");
  return detail?.message || "Não foi possível concluir.";
}

function createApi(apiBase) {
  return async (path, options = {}) => {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      signal: options.signal || AbortSignal.timeout(30000),
      cache: options.method && options.method !== "GET" ? undefined : "no-store",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const body = await response.json();
    if (!response.ok) throw new Error(errorMessage(body.detail));
    return body;
  };
}

function StatusIcon({ state }) {
  if (state === "good") return <CheckCircle2 size={16}/>;
  if (state === "unknown" || state === "not_applicable") return <AlertTriangle size={16}/>;
  return <XCircle size={16}/>;
}

function SearchStep({ api, capabilities, leads, archivedLoaded, archivedLoading, archivedNextCursor, onLoadArchived, onSelect, notify }) {
  const [source, setSource] = useState("search");
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [selectedLead, setSelectedLead] = useState("");
  const [leadQuery, setLeadQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (source === "lead") {
      const lead = leads.find((item) => item.place_id === selectedLead);
      if (!lead) return notify("Selecione um lead existente.");
      const leadAddress = String(lead.address || "").trim();
      const neighborhood = String(lead.neighborhood || neighborhoodFromAddress(leadAddress)).trim();
      const leadLocation = [neighborhood, lead.city, lead.state].filter((value, index, items) => value && items.findIndex((item) => item?.toLocaleLowerCase("pt-BR") === value.toLocaleLowerCase("pt-BR")) === index).join(", ") || leadAddress;
      onSelect({
        name: lead.company_name,
        category: "Categoria a confirmar",
        address: leadAddress || leadLocation || "Localização a confirmar",
        neighborhood,
        city: lead.city || "",
        state: lead.state || "",
        rating: lead.rating,
        review_count: lead.review_count,
        place_id: lead.place_id,
        maps_url: lead.maps_link,
        phone: lead.phone || "",
        lead_place_id: lead.place_id,
        from_lead: true,
      });
      return;
    }
    setLoading(true);
    try {
      const demo = !capabilities.live_configured;
      const payload = await api(`/api/google-analysis/companies/search?demo=${demo}`, {
        method: "POST",
        body: JSON.stringify({ name, address }),
      });
      setResults(payload.items || []);
      if (!(payload.items || []).length) notify("Nenhuma empresa encontrada. Confira o nome e o endereço completo.");
    } catch (error) {
      notify(error.message);
    } finally {
      setLoading(false);
    }
  };

  return <div className="ga-search-layout">
    <section className="ga-card ga-search-card">
      <div className="ga-section-title"><span><Search size={19}/></span><div><h2>Encontre o perfil da empresa</h2><p>Busque pelo nome ou reaproveite um lead já salvo.</p></div></div>
      <div className="ga-source-tabs">
        <button className={source === "search" ? "active" : ""} onClick={() => setSource("search")}><Search size={15}/>Nome e endereço</button>
        <button className={source === "lead" ? "active" : ""} onClick={() => { setSource("lead"); if (!archivedLoaded) onLoadArchived(); }}><Link2 size={15}/>Lead existente</button>
      </div>
      <form onSubmit={submit}>
        {source === "search" ? <>
          <label><span>Nome da empresa no Google Maps</span><div className="ga-input"><Building2 size={17}/><input required minLength="2" value={name} onChange={(event) => setName(event.target.value)} placeholder="Ex: JP do Gás Vicente Pires"/></div></label>
          <label><span>Endereço completo do perfil</span><div className="ga-input"><MapPin size={17}/><input required value={address} onChange={(event) => setAddress(event.target.value)} placeholder="Cole o endereço completo exibido no Google"/></div></label>
        </> : <>
          <label><span>Buscar nos leads carregados</span><div className="ga-input"><Search size={17}/><input value={leadQuery} onChange={(event) => setLeadQuery(event.target.value)} placeholder="Nome ou telefone"/></div></label>
          <label><span>Lead salvo ou perfil arquivado</span><div className="ga-input"><Building2 size={17}/><select required value={selectedLead} onChange={(event) => setSelectedLead(event.target.value)}><option value="">Selecione uma empresa</option>{leads.filter((lead) => { const query = leadQuery.trim().toLocaleLowerCase("pt-BR"); const digits = query.replace(/\D/g, ""); return !query || String(lead.company_name || "").toLocaleLowerCase("pt-BR").includes(query) || (digits.length > 0 && String(lead.phone || "").replace(/\D/g, "").includes(digits)); }).map((lead) => <option key={lead.place_id} value={lead.place_id}>{lead.company_name} · {lead.phone || "telefone não disponível"}{lead.archived ? " · arquivado" : ""}</option>)}</select></div></label>
          {selectedLead && leads.find((lead) => lead.place_id === selectedLead) && <div className="ga-archived-status" role="status">Telefone: {leads.find((lead) => lead.place_id === selectedLead)?.phone || "não disponível — confirme antes de continuar"}</div>}
          {archivedLoading && <div className="ga-archived-status"><LoaderCircle className="spin" size={14}/>Carregando perfis arquivados...</div>}
          {!archivedLoading && archivedNextCursor && <button type="button" className="ga-load-archived" onClick={onLoadArchived}>Carregar mais perfis arquivados</button>}
        </>}
        <button className="ga-primary" disabled={loading}>{loading ? <LoaderCircle className="spin" size={17}/> : <Search size={17}/>} {loading ? "Buscando..." : source === "lead" ? "Usar este lead" : "Buscar minha empresa"}</button>
      </form>
      {capabilities && !capabilities.live_configured && <div className="ga-demo-note"><Sparkles size={17}/><div><strong>Modo demonstração ativo</strong><p>A chave da SerpApi não está configurada. A jornada funciona com dados fictícios claramente identificados.</p></div></div>}
    </section>
    {!!results.length && <section className="ga-card ga-results-card">
      <div className="ga-section-title"><span><Building2 size={19}/></span><div><h2>Empresas encontradas</h2><p>Confirme a empresa correta antes de consumir uma análise.</p></div></div>
      <div className="ga-company-results">{results.map((item, index) => <article key={item.place_id || `${item.name}-${index}`}>
        <div className="ga-company-avatar">{item.name.slice(0, 2).toUpperCase()}</div>
        <div><strong>{item.name}</strong><p>{item.category}</p><small><MapPin size={12}/>{item.address}</small></div>
        <div className="ga-company-rating"><Star size={14}/><b>{item.rating ?? "—"}</b><span>{item.review_count ?? 0} avaliações</span></div>
        <button onClick={() => onSelect(item)}>É esta <ChevronRight size={15}/></button>
      </article>)}</div>
    </section>}
  </div>;
}

function ConfigureStep({ company, demo, onBack, onStart }) {
  const confirmed = (value) => value && !/(confirmar|não informad|nao informad)/i.test(value);
  const neighborhood = company.neighborhood || neighborhoodFromAddress(company.address);
  const localParts = [neighborhood, company.city, company.state].filter((value, index, items) => value && items.findIndex((item) => item?.toLocaleLowerCase("pt-BR") === value.toLocaleLowerCase("pt-BR")) === index);
  const localArea = localParts.join(", ");
  const suggestedLocation = confirmed(localArea) ? localArea : confirmed(company.address) ? company.address : "Brasil";
  const [keyword, setKeyword] = useState(confirmed(company.category) ? company.category : company.name);
  const [location, setLocation] = useState(suggestedLocation);
  const [depth, setDepth] = useState(20);
  return <section className="ga-card ga-config-card">
    <button className="ga-back" onClick={onBack}><ArrowLeft size={15}/>Trocar empresa</button>
    <div className="ga-selected-company"><div className="ga-company-avatar large">{company.name.slice(0, 2).toUpperCase()}</div><div><span>Empresa selecionada</span><h2>{company.name}</h2><p>{company.category} · {company.address}</p></div>{demo && <em>Demonstração</em>}</div>
    <div className="ga-section-title"><span><Target size={19}/></span><div><h2>Confirme a consulta competitiva</h2><p>A posição só vale para esta palavra-chave, localização e momento.</p></div></div>
    <div className="ga-form-row">
      <label><span>Palavra-chave</span><div className="ga-input"><Search size={17}/><input value={keyword} onChange={(event) => setKeyword(event.target.value)} /></div></label>
      <label><span>Localização</span><div className="ga-input"><MapPin size={17}/><input value={location} onChange={(event) => setLocation(event.target.value)} /></div></label>
    </div>
    <label className="ga-depth"><span>Profundidade da busca</span><select value={depth} onChange={(event) => setDepth(Number(event.target.value))}><option value="10">10 resultados</option><option value="20">20 resultados</option></select><small>A primeira versão consulta uma página do Google Maps.</small></label>
    <button className="ga-primary" onClick={() => onStart({ keyword, location, depth })}><Play size={17}/>Iniciar análise</button>
  </section>;
}

function ProgressStep({ job }) {
  const stages = ["Abrindo o perfil público", "Comparando resultados locais", "Aplicando a metodologia ProspectSites", "Relatório preparado para download"];
  return <section className="ga-card ga-progress-card">
    <div className="ga-progress-orbit"><LoaderCircle className="spin" size={35}/><FileSearch size={26}/></div>
    <span>Análise em andamento</span><h2>{job?.stage || "Preparando a análise"}</h2>
    <p>As etapas abaixo refletem operações reais. Não exibimos uma porcentagem fictícia.</p>
    <div className="ga-stage-list">{stages.map((stage) => {
      const done = job?.completed_steps?.some((item) => item.toLowerCase().includes(stage.split(" ")[0].toLowerCase())) || job?.completed_steps?.includes(stage);
      const active = job?.stage === stage;
      return <div className={`${done ? "done" : ""} ${active ? "active" : ""}`} key={stage}>{done ? <CheckCircle2 size={17}/> : active ? <LoaderCircle className="spin" size={17}/> : <Clock3 size={17}/>}<span>{stage}</span></div>;
    })}</div>
  </section>;
}

function ScoreGauge({ report }) {
  const shownScore = report.score_reliable ? report.score : "—";
  return <div className={`ga-score-gauge ${report.score_reliable ? "" : "insufficient"}`} style={{ "--score": `${report.score || 0}%` }}><div><strong>{shownScore}</strong><span>{report.score_reliable ? "/100" : "dados insuficientes"}</span></div></div>;
}

function ReportView({ report, onNew, notify }) {
  const [downloading, setDownloading] = useState("");
  const competition = report.competition || {};
  const positionText = formatMapPosition(competition.position);
  const download = async (format) => {
    setDownloading(format);
    try {
      if (format === "pdf" || format === "both") {
        const { downloadGoogleAnalysisPdf } = await import("./reportPdf");
        downloadGoogleAnalysisPdf(report);
      }
      if (format === "png" || format === "both") await downloadGoogleAnalysisImage(report);
      notify(format === "both" ? "PDF completo e imagem PNG criados." : format === "pdf" ? "PDF completo criado." : "Imagem PNG criada.", true);
    } catch (error) {
      notify(error.message || "Não foi possível gerar o arquivo.");
    } finally {
      setDownloading("");
    }
  };
  return <div className="ga-report" data-lead-place-id={report.lead_place_id || ""} data-demo={report.demo ? "true" : "false"}>
    <div className="ga-ephemeral-banner"><ShieldCheck size={17}/><div><strong>Relatório temporário</strong><span>Os dados já foram removidos do servidor. Baixe os arquivos antes de sair desta tela.</span></div></div>
    {report.demo && <div className="ga-demo-banner"><Sparkles size={17}/><strong>Relatório de demonstração</strong><span>Todos os dados abaixo são fictícios.</span></div>}
    <section className="ga-report-hero ga-card">
      <div className="ga-report-company"><span>Diagnóstico de Perfil da Empresa no Google</span><h1>{report.company.name}</h1><p><MapPin size={14}/>{report.company.address || "Localização não informada"} · <Clock3 size={14}/>{new Date(report.collected_at).toLocaleString("pt-BR")}</p>{report.company.maps_url && <a href={report.company.maps_url} target="_blank" rel="noopener noreferrer">Abrir perfil <ExternalLink size={13}/></a>}</div>
      <ScoreGauge report={report}/>
      <div className="ga-report-actions">
        <button onClick={() => download("pdf")} disabled={Boolean(downloading)}>{downloading === "pdf" ? <LoaderCircle className="spin" size={16}/> : <FileText size={16}/>}Baixar PDF completo</button>
        <button onClick={() => download("png")} disabled={Boolean(downloading)}>{downloading === "png" ? <LoaderCircle className="spin" size={16}/> : <Download size={16}/>}Baixar imagem PNG</button>
        <button className="ga-primary" onClick={() => download("both")} disabled={Boolean(downloading)}>{downloading === "both" ? <LoaderCircle className="spin" size={16}/> : <Download size={16}/>}Baixar PDF + PNG</button>
        <button onClick={onNew}><RefreshCw size={16}/>Nova análise</button>
      </div>
    </section>
    <section className="ga-report-metrics">
      <article><Star size={18}/><div><small>Nota dos clientes</small><strong>{report.company.rating ?? "—"}</strong><span>{report.company.review_count ?? 0} avaliações</span></div></article>
      <article><Target size={18}/><div><small>Posição observada</small><strong>{positionText}</strong><span>{competition.keyword}</span></div></article>
      <article><ShieldCheck size={18}/><div><small>Cobertura</small><strong>{Math.round(report.coverage)}%</strong><span>dos pesos avaliáveis</span></div></article>
      <article><Sparkles size={18}/><div><small>Melhorias confirmadas</small><strong>{report.improvements_count}</strong><span>entre 16 itens</span></div></article>
      <article><Coins size={18}/><div><small>Consumo estimado</small><strong>{report.cost?.searches_used ?? 0}</strong><span>buscas · ~US$ {(report.cost?.estimated_usd ?? 0).toFixed(3)}</span></div></article>
    </section>
    <section className="ga-card ga-summary"><div className="ga-section-title"><span><BarChart3 size={19}/></span><div><h2>Resumo executivo</h2><p>Metodologia ProspectSites {report.methodology_version}</p></div></div><p>{report.summary}</p>{!report.score_reliable && <div className="ga-warning"><AlertTriangle size={17}/>Cobertura abaixo de {report.minimum_coverage}%. A nota não deve ser tratada como confiável.</div>}</section>
    <section className="ga-priorities"><div className="ga-section-title"><span><Target size={19}/></span><div><h2>Ações prioritárias</h2><p>Ordenadas por evidência, impacto e possibilidade de ação.</p></div></div><div className="ga-priority-grid">{report.priorities?.map((priority, index) => <article key={priority.key}><span>0{index + 1}</span><h3>{priority.title}</h3><p>{priority.reason}</p><strong>Ação recomendada</strong><small>{priority.action}</small></article>)}</div></section>
    <section className="ga-card ga-checklist"><div className="ga-section-title"><span><ShieldCheck size={19}/></span><div><h2>Checklist completo</h2><p>Desconhecido e não aplicável não recebem zero.</p></div></div><div className="ga-check-grid">{report.checklist?.map((item) => <article className={item.state} key={item.key}><StatusIcon state={item.state}/><div><strong>{item.label}</strong><span>{item.state_label}</span><p>{item.evidence}</p></div><em>{item.points === null ? "—" : `${item.points}/${item.weight}`}</em></article>)}</div></section>
    <section className="ga-card ga-competition"><div className="ga-section-title"><span><BarChart3 size={19}/></span><div><h2>Comparação competitiva</h2><p>{competition.keyword} · {competition.location}</p></div></div><div className="ga-competition-summary"><span>Posição observada <b>{positionText}</b></span><span>Amostra <b>{competition.sample_size}</b></span><span>Mediana de avaliações <b>{competition.median_review_count ?? "—"}</b></span></div><div className="ga-competitor-list">{competition.competitors?.map((item) => <article key={item.place_id || item.name}><b>{item.position}º</b><div><strong>{item.name}</strong><span><Star size={12}/>{item.rating ?? "—"} · {item.review_count ?? 0} avaliações</span></div></article>)}</div></section>
    <section className="ga-card ga-limitations"><div className="ga-section-title"><span><AlertTriangle size={19}/></span><div><h2>Fontes e limitações</h2><p>Transparência faz parte da análise.</p></div></div><ul>{report.limitations?.map((item) => <li key={item}>{item}</li>)}</ul><p className="ga-method-note">A Nota ProspectSites é própria e não representa uma nota do Google. Os pesos não são fatores oficiais de ranqueamento.</p></section>
  </div>;
}

export default function GoogleAnalysisPage({ apiBase, leads = [] }) {
  const api = useMemo(() => createApi(apiBase), [apiBase]);
  const [step, setStep] = useState("search");
  const [capabilities, setCapabilities] = useState(null);
  const [capabilitiesError, setCapabilitiesError] = useState("");
  const [company, setCompany] = useState(null);
  const [job, setJob] = useState(null);
  const [report, setReport] = useState(null);
  const [archivedLeads, setArchivedLeads] = useState([]);
  const [archivedCursor, setArchivedCursor] = useState(null);
  const [archivedLoaded, setArchivedLoaded] = useState(false);
  const [archivedLoading, setArchivedLoading] = useState(false);
  const [notice, setNotice] = useState(null);
  const notify = (message, success = false) => { setNotice({ message, success }); window.setTimeout(() => setNotice(null), 5000); };

  useEffect(() => { api("/api/google-analysis/capabilities").then(setCapabilities).catch((error) => { setCapabilitiesError(error.message); notify(error.message); }); }, [api]);

  const availableLeads = useMemo(() => {
    const byId = new Map(archivedLeads.map((lead) => [lead.place_id, lead]));
    leads.forEach((lead) => byId.set(lead.place_id, lead));
    return [...byId.values()].sort((a, b) => a.company_name.localeCompare(b.company_name, "pt-BR"));
  }, [archivedLeads, leads]);

  const loadArchivedLeads = async () => {
    if (archivedLoading || (archivedLoaded && !archivedCursor)) return;
    setArchivedLoading(true);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (archivedCursor) params.set("cursor", archivedCursor);
      const result = await api(`/api/leads/archived-profiles?${params.toString()}`);
      setArchivedLeads((current) => {
        const byId = new Map(current.map((lead) => [lead.place_id, lead]));
        (result.items || []).forEach((lead) => byId.set(lead.place_id, lead));
        return [...byId.values()];
      });
      setArchivedCursor(result.next_cursor || null);
      setArchivedLoaded(true);
    } catch (error) {
      notify(error.message);
    } finally {
      setArchivedLoading(false);
    }
  };

  const selectCompany = (item) => { setCompany(item); setStep("configure"); };
  const start = async (config) => {
    try {
      const nextJob = await api("/api/google-analysis/jobs", { method: "POST", body: JSON.stringify({ company, ...config, lead_place_id: company.lead_place_id || null, demo: !capabilities.live_configured }) });
      setJob(nextJob); setStep("progress");
      let current = nextJob;
      const deadline = Date.now() + 180000;
      let consecutiveErrors = 0;
      while (Date.now() < deadline && ["pending", "processing"].includes(current.status)) {
        await wait(1500);
        try {
          current = await api(`/api/google-analysis/jobs/${current.id}`);
          consecutiveErrors = 0;
          setJob(current);
        } catch (error) {
          consecutiveErrors += 1;
          if (consecutiveErrors >= 3) throw new Error("Não foi possível acompanhar a análise. Confirme o estado antes de iniciar outra para evitar consumo duplicado.");
        }
      }
      if (current.status === "failed") throw new Error(current.error || "A análise falhou.");
      if (!current.report_id) throw new Error("A análise não terminou dentro do tempo esperado.");
      const result = await api(`/api/google-analysis/reports/${current.report_id}`);
      setReport(result); setStep("report");
    } catch (error) { notify(error.message); setStep("configure"); }
  };
  const reset = () => { setCompany(null); setJob(null); setReport(null); setStep("search"); };

  return <div className="ga-page">
    <header className="ga-hero"><div><span className="ga-kicker"><Sparkles size={14}/>Inteligência local ProspectSites</span><h1>Análise Google</h1><p>Diagnóstico transparente do perfil, reputação e concorrência local.</p></div><div className="ga-storage-note"><ShieldCheck size={16}/><span>Nenhuma análise é salva no banco</span></div></header>
    {!capabilities ? <div className="ga-archived-status" role="status">{capabilitiesError ? <><AlertTriangle size={14}/>Não foi possível verificar a análise. Atualize a página para tentar novamente.</> : <><LoaderCircle className="spin" size={14}/>Verificando disponibilidade da análise...</>}</div> : step === "search" ? <SearchStep api={api} capabilities={capabilities} leads={availableLeads} archivedLoaded={archivedLoaded} archivedLoading={archivedLoading} archivedNextCursor={archivedCursor} onLoadArchived={loadArchivedLeads} onSelect={selectCompany} notify={notify}/> : step === "configure" ? <ConfigureStep company={company} demo={!capabilities.live_configured} onBack={() => setStep("search")} onStart={start}/> : step === "progress" ? <ProgressStep job={job}/> : report ? <ReportView report={report} onNew={reset} notify={notify}/> : null}
    {notice && <div role={notice.success ? "status" : "alert"} className={`ga-notice ${notice.success ? "success" : ""}`}>{notice.success ? <CheckCircle2 size={17}/> : <AlertTriangle size={17}/>}<span>{notice.message}</span><button onClick={() => setNotice(null)}>×</button></div>}
  </div>;
}
