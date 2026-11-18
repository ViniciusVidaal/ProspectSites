import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown, ArrowUp, CalendarDays, Check, ChevronLeft, ChevronRight, CircleDot,
  Columns3, Filter, Inbox, LoaderCircle, MessageCircle, MoreHorizontal,
  History, Phone, Plus, RefreshCw, Save, Search, Settings2, Trash2, Wifi, X,
} from "lucide-react";
import { createCrmApi } from "./api";
import "./crm.css";

const EMPTY_DASHBOARD = { stages: [], instances: [], contacts: [], counts: {}, total_contacts: 0 };

function dayKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function DateRangeFilter({ onApply }) {
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [applied, setApplied] = useState(null);
  const firstDay = new Date(month.getFullYear(), month.getMonth(), 1).getDay();
  const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const label = applied ? `${applied[0].split("-").reverse().join("/")} – ${applied[1].split("-").reverse().join("/")}` : "Selecionar período";
  function selectDay(day) {
    const value = dayKey(new Date(month.getFullYear(), month.getMonth(), day));
    if (!start || end) { setStart(value); setEnd(""); }
    else if (value < start) { setEnd(start); setStart(value); }
    else setEnd(value);
  }
  return <div className="crm-date-picker">
    <button type="button" className="crm-date-trigger" onClick={() => setOpen(!open)} aria-expanded={open}><CalendarDays size={14}/>{label}</button>
    {open && <div className="crm-calendar" role="dialog" aria-label="Selecionar período">
      <div className="crm-calendar-head"><button type="button" aria-label="Mês anterior" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft size={16}/></button><strong>{month.toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}</strong><button type="button" aria-label="Próximo mês" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight size={16}/></button></div>
      <div className="crm-calendar-grid">{["D", "S", "T", "Q", "Q", "S", "S"].map((d, i) => <span key={i}>{d}</span>)}{Array.from({ length: firstDay }, (_, i) => <span key={`blank-${i}`}/>)}{Array.from({ length: days }, (_, i) => { const day = i + 1; const value = dayKey(new Date(month.getFullYear(), month.getMonth(), day)); return <button type="button" key={day} className={`${value === start || value === end ? "selected" : ""} ${start && end && value > start && value < end ? "in-range" : ""}`} onClick={() => selectDay(day)} aria-label={`${day} de ${month.toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}`} aria-pressed={value === start || value === end}>{day}</button>; })}</div>
      <p>{!start ? "Selecione o primeiro dia" : !end ? "Selecione o último dia" : "Período selecionado"}</p>
      <div className="crm-calendar-actions"><button type="button" onClick={() => { setStart(""); setEnd(""); setApplied(null); onApply("", ""); setOpen(false); }}>Limpar</button><button type="button" disabled={!start || !end} onClick={() => { setApplied([start, end]); onApply(start, end); setOpen(false); }}>Buscar</button></div>
    </div>}
  </div>;
}

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function initials(name) {
  return String(name || "Lead").split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

function instanceMeta(instances, name) {
  return instances.find((item) => item.instance_name === name) || {
    label: name || "WhatsApp", color: "#16a36a", instance_name: name,
  };
}

function InstanceBadge({ instances, name }) {
  const item = instanceMeta(instances, name);
  return <span className="crm-instance-badge" style={{ "--instance-color": item.color }}>{item.label}</span>;
}

function LeadCard({ contact, instances, onOpen, onDragStart }) {
  return (
    <article
      className="crm-lead-card"
      draggable
      onDragStart={(event) => onDragStart(event, contact.id)}
      onClick={() => onOpen(contact)}
      tabIndex="0"
      onKeyDown={(event) => { if (event.key === "Enter") onOpen(contact); }}
    >
      <div className="crm-card-head">
        <span className="crm-avatar">{initials(contact.name)}</span>
        <div><strong>{contact.name || contact.phone}</strong><small><Phone size={11}/>{contact.phone}</small></div>
        <MoreHorizontal size={16}/>
      </div>
      <p>{contact.last_message || "Nenhuma mensagem disponível"}</p>
      <div className="crm-card-dates"><span>Primeiro <strong>{formatDate(contact.first_contact_at)}</strong></span><span>Último <strong>{formatDate(contact.last_interaction_at)}</strong></span></div>
      <div className="crm-card-foot">
        <InstanceBadge instances={instances} name={contact.last_instance_name}/>
        <time>{contact.responsible || "Sem responsável"}</time>
      </div>
    </article>
  );
}

function LeadDetails({ contact, stages, instances, messages, activities, loading, onClose, onMove, onResponsible }) {
  const [responsible, setResponsible] = useState(contact?.responsible || "");
  const [savingResponsible, setSavingResponsible] = useState(false);
  useEffect(() => { setResponsible(contact?.responsible || ""); }, [contact]);
  if (!contact) return null;
  const phoneDigits = String(contact.phone || "").replace(/\D/g, "");
  const whatsappPhone = phoneDigits.length === 10 || phoneDigits.length === 11 ? `55${phoneDigits}` : phoneDigits;

  async function saveResponsible() {
    setSavingResponsible(true);
    try { await onResponsible(contact.id, responsible); }
    finally { setSavingResponsible(false); }
  }

  return (
    <div className="crm-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="crm-drawer" aria-label="Detalhes do lead">
        <header>
          <div className="crm-contact-title"><span className="crm-avatar large">{initials(contact.name)}</span><div><h2>{contact.name || contact.phone}</h2><p>{contact.phone}</p></div></div>
          <button className="crm-icon-button" onClick={onClose} aria-label="Fechar"><X size={19}/></button>
        </header>
        <div className="crm-detail-summary">
          <label><span>Etapa comercial</span><select value={contact.stage_id || ""} onChange={(event) => onMove(contact.id, event.target.value)}>{stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></label>
          <div><span>WhatsApp mais recente</span><InstanceBadge instances={instances} name={contact.last_instance_name}/></div>
          <div><span>Primeiro contato</span><strong>{formatDate(contact.first_contact_at)}</strong></div>
          <div><span>Última interação</span><strong>{formatDate(contact.last_interaction_at)}</strong></div>
          {whatsappPhone.length >= 12 && whatsappPhone.length <= 15 && <div><span>Contato</span><a href={`https://wa.me/${whatsappPhone}`} target="_blank" rel="noopener noreferrer">Abrir WhatsApp</a></div>}
          <div><span>Mensagens</span><strong>{contact.message_count || 0}</strong></div>
          <label className="crm-responsible-field"><span>Responsável</span><div><input value={responsible} onChange={(event) => setResponsible(event.target.value)} placeholder="Sem responsável" maxLength="80"/><button onClick={saveResponsible} disabled={savingResponsible} aria-label="Salvar responsável">{savingResponsible ? <LoaderCircle className="spin" size={14}/> : <Save size={14}/>}</button></div></label>
        </div>
        <div className="crm-activity-section">
          <div className="crm-history-head"><div><h3>Movimentações</h3><p>Histórico comercial do lead</p></div><span><History size={14}/>{activities.length}</span></div>
          <div className="crm-activity-list">{activities.map((activity) => <article key={activity.id}><i/><div><strong>{activity.action === "stage_moved" ? "Etapa alterada" : "Cadastro atualizado"}</strong><p>{activity.reason || (activity.actor === "hermes" ? "Ação executada pelo Hermes" : "Alteração manual no CRM")}</p></div><time>{formatDate(activity.created_at)}</time></article>)}{!activities.length && <p className="crm-no-activity">Nenhuma movimentação registrada.</p>}</div>
        </div>
        <div className="crm-history-head"><div><h3>Histórico de mensagens</h3><p>Consulta somente leitura</p></div><span><MessageCircle size={14}/>{messages.length}</span></div>
        <div className="crm-message-history">
          {loading && <div className="crm-loading"><LoaderCircle className="spin" size={20}/>Carregando mensagens...</div>}
          {!loading && messages.map((message) => (
            <div className={`crm-message ${message.from_me ? "outbound" : "inbound"}`} key={message.id}>
              <small>{message.from_me ? "Enviada pelo celular" : contact.name || "Contato"}</small>
              <p>{message.text}</p>
              <footer><InstanceBadge instances={instances} name={message.instance_name}/><time>{formatDate(message.message_timestamp)}</time></footer>
            </div>
          ))}
          {!loading && !messages.length && <div className="crm-empty compact"><MessageCircle size={25}/><strong>Sem mensagens armazenadas</strong><span>O histórico aparecerá após o primeiro webhook recebido.</span></div>}
        </div>
      </aside>
    </div>
  );
}

function StageManager({ stages, api, onChanged, notify }) {
  const [name, setName] = useState("");
  const [color, setColor] = useState("#16a36a");
  const [busy, setBusy] = useState(false);

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/api/crm/stages", { method: "POST", body: JSON.stringify({ name, color }) });
      setName("");
      await onChanged();
    } catch (error) { notify(error.message); } finally { setBusy(false); }
  }

  async function rename(stage) {
    const nextName = window.prompt("Novo nome da etapa", stage.name);
    if (!nextName || nextName.trim() === stage.name) return;
    try {
      await api(`/api/crm/stages/${stage.id}`, { method: "PATCH", body: JSON.stringify({ name: nextName.trim() }) });
      await onChanged();
    } catch (error) { notify(error.message); }
  }

  async function remove(stage) {
    const fallback = stages.find((item) => item.id !== stage.id);
    if (!fallback || !window.confirm(`Excluir a etapa “${stage.name}”? Os leads serão movidos para “${fallback.name}”.`)) return;
    try {
      await api(`/api/crm/stages/${stage.id}/delete`, { method: "POST", body: JSON.stringify({ move_to_stage_id: fallback.id }) });
      await onChanged();
    } catch (error) { notify(error.message); }
  }

  async function move(index, direction) {
    const next = [...stages];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    try {
      await api("/api/crm/stages/reorder", { method: "PUT", body: JSON.stringify({ stage_ids: next.map((item) => item.id) }) });
      await onChanged();
    } catch (error) { notify(error.message); }
  }

  return (
    <section className="crm-settings-card">
      <div className="crm-settings-title"><span><Columns3 size={18}/></span><div><h2>Etapas do Kanban</h2><p>Adicione, renomeie, exclua ou reorganize as colunas.</p></div></div>
      <div className="crm-stage-list">{stages.map((stage, index) => <article key={stage.id}><i style={{ background: stage.color }}/><strong>{stage.name}</strong><div><button onClick={() => move(index, -1)} disabled={index === 0}><ArrowUp size={14}/></button><button onClick={() => move(index, 1)} disabled={index === stages.length - 1}><ArrowDown size={14}/></button><button onClick={() => rename(stage)}>Editar</button><button className="danger" onClick={() => remove(stage)}><Trash2 size={14}/></button></div></article>)}</div>
      <form className="crm-add-stage" onSubmit={create}><input type="color" value={color} onChange={(event) => setColor(event.target.value)}/><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Nome da nova etapa" minLength="2" required/><button disabled={busy}><Plus size={15}/>Adicionar etapa</button></form>
    </section>
  );
}

function InstanceManager({ instances, api, onChanged, notify }) {
  const [form, setForm] = useState({ instance_name: "", label: "", phone: "", color: "#16a36a", provider: "hermes" });
  const [busy, setBusy] = useState("");

  async function create(event) {
    event.preventDefault();
    setBusy("create");
    try {
      await api("/api/crm/instances", { method: "POST", body: JSON.stringify(form) });
      setForm({ instance_name: "", label: "", phone: "", color: "#16a36a", provider: "hermes" });
      await onChanged();
    } catch (error) { notify(error.message); } finally { setBusy(""); }
  }

  return (
    <section className="crm-settings-card">
      <div className="crm-settings-title"><span><Wifi size={18}/></span><div><h2>Canais do WhatsApp</h2><p>Cadastre até quatro conexões que serão alimentadas pelo Hermes/Baileys.</p></div></div>
      <div className="crm-instance-list">{instances.map((instance) => <article key={instance.instance_name}><i style={{ background: instance.color }}/><div><strong>{instance.label}</strong><small>{instance.phone || instance.instance_name} · {instance.provider === "manual" ? "Manual" : "Hermes"}</small></div><span className={`crm-status ${instance.status === "connected" || instance.status === "open" ? "online" : ""}`}><CircleDot size={12}/>{instance.status || "aguardando Hermes"}</span></article>)}</div>
      {instances.length < 4 && <form className="crm-instance-form" onSubmit={create}><label><span>Identificador técnico</span><input value={form.instance_name} onChange={(event) => setForm({ ...form, instance_name: event.target.value })} placeholder="whatsapp-01" pattern="[A-Za-z0-9_-]+" required/></label><label><span>Nome visível</span><input value={form.label} onChange={(event) => setForm({ ...form, label: event.target.value })} placeholder="WhatsApp 01" required/></label><label><span>Número</span><input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} placeholder="55 11 99999-9999"/></label><label className="color-field"><span>Cor</span><input type="color" value={form.color} onChange={(event) => setForm({ ...form, color: event.target.value })}/></label><button disabled={busy === "create"}><Plus size={15}/>Cadastrar instância</button></form>}
    </section>
  );
}

export default function CrmPage({ apiBase }) {
  const api = useMemo(() => createCrmApi(apiBase), [apiBase]);
  const [dashboard, setDashboard] = useState(EMPTY_DASHBOARD);
  const [view, setView] = useState("kanban");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState(null);
  const [query, setQuery] = useState("");
  const [instanceFilter, setInstanceFilter] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [activities, setActivities] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const notify = useCallback((message, success = false) => {
    setNotice({ message, success });
    window.setTimeout(() => setNotice(null), 4500);
  }, []);

  const loadDashboard = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const suffix = instanceFilter ? `?instance_name=${encodeURIComponent(instanceFilter)}` : "";
      setDashboard(await api(`/api/crm/dashboard${suffix}`));
    } catch (error) { notify(error.message); } finally { if (!silent) setLoading(false); }
  }, [api, instanceFilter, notify]);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  const contacts = useMemo(() => dashboard.contacts.filter((contact) => {
    const text = `${contact.name || ""} ${contact.phone || ""}`.toLowerCase();
    const interaction = contact.last_interaction_at ? new Date(contact.last_interaction_at) : null;
    const start = dateFrom ? new Date(`${dateFrom}T00:00:00`) : null;
    const end = dateTo ? new Date(`${dateTo}T23:59:59.999`) : null;
    return (!query || text.includes(query.toLowerCase()))
      && (!stageFilter || contact.stage_id === stageFilter)
      && (!start || (interaction && interaction >= start))
      && (!end || (interaction && interaction <= end));
  }), [dashboard.contacts, query, stageFilter, dateFrom, dateTo]);

  async function openContact(contact) {
    setSelected(contact);
    setMessagesLoading(true);
    try {
      const [nextMessages, nextActivities] = await Promise.all([
        api(`/api/crm/contacts/${contact.id}/messages`),
        api(`/api/crm/contacts/${contact.id}/activities`),
      ]);
      setMessages(nextMessages);
      setActivities(nextActivities);
    }
    catch (error) { notify(error.message); }
    finally { setMessagesLoading(false); }
  }

  async function updateResponsible(contactId, responsible) {
    try {
      const updated = await api(`/api/crm/contacts/${contactId}`, { method: "PATCH", body: JSON.stringify({ responsible: responsible.trim() }) });
      setDashboard((current) => ({ ...current, contacts: current.contacts.map((item) => item.id === contactId ? updated : item) }));
      setSelected(updated);
      setActivities(await api(`/api/crm/contacts/${contactId}/activities`));
      notify("Responsável atualizado.", true);
    } catch (error) { notify(error.message); throw error; }
  }

  async function moveContact(contactId, stageId) {
    const previous = dashboard;
    const update = (contact) => contact.id === contactId ? { ...contact, stage_id: stageId } : contact;
    setDashboard({ ...dashboard, contacts: dashboard.contacts.map(update) });
    setSelected((contact) => contact?.id === contactId ? update(contact) : contact);
    try {
      const updated = await api(`/api/crm/contacts/${contactId}/stage`, { method: "PUT", body: JSON.stringify({ stage_id: stageId }) });
      if (selected?.id === contactId) {
        setSelected(updated);
        setActivities(await api(`/api/crm/contacts/${contactId}/activities`));
      }
    } catch (error) { setDashboard(previous); notify(error.message); }
  }

  function dragStart(event, contactId) { event.dataTransfer.setData("text/crm-contact", contactId); event.dataTransfer.effectAllowed = "move"; }
  function drop(event, stageId) { event.preventDefault(); const contactId = event.dataTransfer.getData("text/crm-contact"); if (contactId) moveContact(contactId, stageId); }

  return (
    <section className="crm-page">
      {notice && <div className={`crm-notice ${notice.success ? "success" : ""}`}>{notice.success && <Check size={15}/>}<span>{notice.message}</span><button onClick={() => setNotice(null)}><X size={14}/></button></div>}
      <div className="crm-toolbar">
        <div className="crm-tabs"><button className={view === "kanban" ? "active" : ""} onClick={() => setView("kanban")}><Columns3 size={15}/>Kanban</button><button className={view === "conversations" ? "active" : ""} onClick={() => setView("conversations")}><Inbox size={15}/>Conversas</button><button className={view === "integrations" ? "active" : ""} onClick={() => setView("integrations")}><Settings2 size={15}/>Integrações</button></div>
        {view !== "integrations" && <div className="crm-filters"><label><Search size={15}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nome ou telefone"/></label><label><Filter size={14}/><select value={instanceFilter} onChange={(event) => setInstanceFilter(event.target.value)}><option value="">Todos os WhatsApps</option>{dashboard.instances.map((item) => <option key={item.id} value={item.instance_name}>{item.label}</option>)}</select></label><label><select value={stageFilter} onChange={(event) => setStageFilter(event.target.value)}><option value="">Todas as etapas</option>{dashboard.stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></label><DateRangeFilter onApply={(from, to) => { setDateFrom(from); setDateTo(to); }}/><button className="crm-refresh" onClick={() => loadDashboard()} disabled={loading} aria-label="Atualizar CRM"><RefreshCw className={loading ? "spin" : ""} size={16}/></button></div>}
      </div>

      {loading && !dashboard.stages.length && <div className="crm-loading page"><LoaderCircle className="spin" size={26}/>Preparando o CRM...</div>}
      {!loading && view === "kanban" && <div className="crm-kanban">{dashboard.stages.map((stage) => {
        const stageContacts = contacts.filter((contact) => contact.stage_id === stage.id);
        return <section className="crm-column" key={stage.id} onDragOver={(event) => event.preventDefault()} onDrop={(event) => drop(event, stage.id)}><header><div><i style={{ background: stage.color }}/><strong>{stage.name}</strong></div><span>{stageContacts.length}</span></header><div className="crm-column-body">{stageContacts.map((contact) => <LeadCard key={contact.id} contact={contact} instances={dashboard.instances} onOpen={openContact} onDragStart={dragStart}/>)}{!stageContacts.length && <div className="crm-drop-zone">Arraste um lead para esta etapa</div>}</div></section>;
      })}</div>}

      {!loading && view === "conversations" && <div className="crm-conversations"><div className="crm-conversation-list">{contacts.map((contact) => <button key={contact.id} onClick={() => openContact(contact)}><span className="crm-avatar">{initials(contact.name)}</span><div><strong>{contact.name || contact.phone}</strong><p>{contact.last_message || "Sem prévia"}</p><footer><InstanceBadge instances={dashboard.instances} name={contact.last_instance_name}/><time>{formatDate(contact.last_interaction_at)}</time></footer></div><span className="crm-message-count">{contact.message_count || 0}</span><ChevronRight size={16}/></button>)}{!contacts.length && <div className="crm-empty"><Inbox size={30}/><strong>Nenhuma conversa encontrada</strong><span>Altere os filtros ou aguarde o recebimento de mensagens.</span></div>}</div></div>}

      {!loading && view === "integrations" && <div className="crm-settings-grid"><InstanceManager instances={dashboard.instances} api={api} onChanged={loadDashboard} notify={notify}/><StageManager stages={dashboard.stages} api={api} onChanged={loadDashboard} notify={notify}/><aside className="crm-readonly-note"><MessageCircle size={19}/><div><strong>CRM preparado para o Hermes</strong><p>O Hermes poderá sincronizar mensagens, atualizar conexões e mover leads automaticamente. Até a integração ser ativada, o Kanban e as movimentações manuais continuam funcionando normalmente.</p></div></aside></div>}

      <LeadDetails contact={selected} stages={dashboard.stages} instances={dashboard.instances} messages={messages} activities={activities} loading={messagesLoading} onClose={() => { setSelected(null); setMessages([]); setActivities([]); }} onMove={moveContact} onResponsible={updateResponsible}/>
    </section>
  );
}

