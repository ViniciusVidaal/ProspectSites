import csv
import io
import json
import re
import shutil
import sqlite3
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import requests
from rapidfuzz import fuzz

RECEITA_WEBDAV = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
RECEITA_SHARE = "YggdBLfdninEJX9"
LEGAL_WORDS = {
    "a", "as", "da", "das", "de", "do", "dos", "e", "em", "empresa",
    "grupo", "ltda", "limitada", "me", "mei", "eireli", "epp", "sa",
    "servicos", "comercio", "industria", "brasil",
}
DDD_UF = {
    "11":"SP","12":"SP","13":"SP","14":"SP","15":"SP","16":"SP","17":"SP","18":"SP","19":"SP",
    "21":"RJ","22":"RJ","24":"RJ","27":"ES","28":"ES","31":"MG","32":"MG","33":"MG","34":"MG","35":"MG","37":"MG","38":"MG",
    "41":"PR","42":"PR","43":"PR","44":"PR","45":"PR","46":"PR","47":"SC","48":"SC","49":"SC","51":"RS","53":"RS","54":"RS","55":"RS",
    "61":"DF","62":"GO","64":"GO","63":"TO","65":"MT","66":"MT","67":"MS","68":"AC","69":"RO",
    "71":"BA","73":"BA","74":"BA","75":"BA","77":"BA","79":"SE","81":"PE","87":"PE","82":"AL","83":"PB","84":"RN","85":"CE","88":"CE","86":"PI","89":"PI",
    "91":"PA","93":"PA","94":"PA","92":"AM","97":"AM","95":"RR","96":"AP","98":"MA","99":"MA",
}


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9]+", " ", value)).strip().upper()


def compact_name(value):
    return " ".join(word for word in normalize(value).split() if word.lower() not in LEGAL_WORDS)


def _webdav_list(path=""):
    url = RECEITA_WEBDAV + path.strip("/") + ("/" if path else "")
    response = requests.request(
        "PROPFIND", url, auth=(RECEITA_SHARE, ""),
        headers={"Depth": "1"}, timeout=60,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    return [item.findtext("{DAV:}href", "") for item in root.findall("{DAV:}response")][1:]


def official_month_url():
    months = sorted({match for href in _webdav_list() for match in re.findall(r"(\d{4}-\d{2})", href)})
    if not months:
        raise RuntimeError("Não foi possível localizar a publicação mensal da Receita.")
    return months[-1], months[-1]


def list_zip_urls(month_url, label):
    names = [href.rstrip("/").rsplit("/", 1)[-1] for href in _webdav_list(month_url)]
    return [f"{RECEITA_WEBDAV}{month_url}/{name}" for name in sorted(names) if label.lower() in name.lower() and name.lower().endswith(".zip")]


def download(url, destination):
    destination = Path(destination)
    with requests.get(url, auth=(RECEITA_SHARE, ""), stream=True, timeout=180) as response:
        response.raise_for_status()
        with destination.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    output.write(chunk)
    return destination


def csv_rows_from_zip(path):
    with zipfile.ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if not name.endswith("/"))
        with archive.open(member) as binary:
            text = io.TextIOWrapper(binary, encoding="latin-1", errors="replace", newline="")
            yield from csv.reader(text, delimiter=";", quotechar='"')


def open_database(path):
    connection = sqlite3.connect(path, timeout=60)
    connection.execute("PRAGMA busy_timeout=60000")
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("CREATE TABLE IF NOT EXISTS municipios (codigo TEXT PRIMARY KEY, nome TEXT)")
    connection.execute("""CREATE TABLE IF NOT EXISTS candidatos (
        cnpj TEXT PRIMARY KEY, basico TEXT, fantasia TEXT, razao TEXT DEFAULT '',
        cidade TEXT, uf TEXT, situacao TEXT
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_candidatos_uf ON candidatos(uf)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_candidatos_basico ON candidatos(basico)")
    connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS candidate_search USING fts5(search_text)")
    return connection


def build_regional_index(database_path, target_ufs, progress=print):
    database_path = Path(database_path)
    if str(database_path).startswith("/content/"):
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(f"{database_path}{suffix}").unlink(missing_ok=True)
    work = Path("/content/cnpj_receita_work")
    work.mkdir(parents=True, exist_ok=True)
    connection = open_database(database_path)
    month_url, month = official_month_url()
    progress(f"Base oficial localizada: {month}")

    municipality_url = list_zip_urls(month_url, "Municipios")[0]
    archive = download(municipality_url, work / "municipios.zip")
    connection.execute("DELETE FROM municipios")
    connection.executemany("INSERT OR REPLACE INTO municipios VALUES (?, ?)", ((row[0], normalize(row[1])) for row in csv_rows_from_zip(archive)))
    connection.commit()
    archive.unlink(missing_ok=True)

    connection.execute("DELETE FROM candidatos")
    establishment_urls = list_zip_urls(month_url, "Estabelecimentos")
    for number, url in enumerate(establishment_urls, 1):
        progress(f"Estabelecimentos {number}/{len(establishment_urls)}")
        archive = download(url, work / "estabelecimentos.zip")
        batch = []
        for row in csv_rows_from_zip(archive):
            if len(row) < 21 or row[19].upper() not in target_ufs:
                continue
            city = connection.execute("SELECT nome FROM municipios WHERE codigo=?", (row[20],)).fetchone()
            batch.append((row[0] + row[1] + row[2], row[0], row[4], city[0] if city else "", row[19].upper(), row[5]))
            if len(batch) >= 5000:
                connection.executemany("INSERT OR REPLACE INTO candidatos(cnpj,basico,fantasia,cidade,uf,situacao) VALUES (?,?,?,?,?,?)", batch)
                connection.commit(); batch.clear()
        if batch:
            connection.executemany("INSERT OR REPLACE INTO candidatos(cnpj,basico,fantasia,cidade,uf,situacao) VALUES (?,?,?,?,?,?)", batch)
            connection.commit()
        archive.unlink(missing_ok=True)

    basics = {row[0] for row in connection.execute("SELECT DISTINCT basico FROM candidatos")}
    company_urls = list_zip_urls(month_url, "Empresas")
    for number, url in enumerate(company_urls, 1):
        progress(f"Razões sociais {number}/{len(company_urls)}")
        archive = download(url, work / "empresas.zip")
        batch = []
        for row in csv_rows_from_zip(archive):
            if row and row[0] in basics:
                batch.append((row[1], row[0]))
            if len(batch) >= 5000:
                connection.executemany("UPDATE candidatos SET razao=? WHERE basico=?", batch)
                connection.commit(); batch.clear()
        if batch:
            connection.executemany("UPDATE candidatos SET razao=? WHERE basico=?", batch)
            connection.commit()
        archive.unlink(missing_ok=True)

    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
    connection.execute("INSERT OR REPLACE INTO metadata VALUES ('month', ?)", (month,))
    connection.execute("DROP TABLE IF EXISTS candidate_search")
    connection.execute("CREATE VIRTUAL TABLE candidate_search USING fts5(search_text)")
    search_batch = []
    for rowid, fantasy, legal in connection.execute("SELECT rowid,fantasia,razao FROM candidatos"):
        search_batch.append((rowid, compact_name(f"{fantasy} {legal}")))
        if len(search_batch) >= 10000:
            connection.executemany("INSERT INTO candidate_search(rowid,search_text) VALUES (?,?)", search_batch)
            search_batch.clear()
    if search_batch:
        connection.executemany("INSERT INTO candidate_search(rowid,search_text) VALUES (?,?)", search_batch)
    connection.commit()
    count = connection.execute("SELECT COUNT(*) FROM candidatos").fetchone()[0]
    connection.close()
    shutil.rmtree(work, ignore_errors=True)
    progress(f"Índice concluído: {count:,} estabelecimentos em {', '.join(sorted(target_ufs))}")
    return count


def infer_uf(phone, saved_state=""):
    state = normalize(saved_state)
    if len(state) == 2:
        return state
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("55"):
        digits = digits[2:]
    return DDD_UF.get(digits[:2], "")


def match_lead(connection, company_name, city="", state="", phone=""):
    wanted = compact_name(company_name)
    if len(wanted) < 3:
        return None
    uf = infer_uf(phone, state)
    city_normalized = normalize(city)
    search_tokens = sorted({token for token in wanted.split() if len(token) >= 3}, key=len, reverse=True)[:4]
    if not search_tokens:
        return None
    fts_query = " OR ".join(f'"{token}"' for token in search_tokens)
    rows = connection.execute(
        """SELECT c.cnpj,c.fantasia,c.razao,c.cidade,c.uf,c.situacao
           FROM candidate_search s JOIN candidatos c ON c.rowid=s.rowid
           WHERE candidate_search MATCH ? AND (?='' OR c.uf=?) LIMIT 5000""",
        (fts_query, uf, uf),
    )
    best = []
    for cnpj, fantasy, legal, candidate_city, candidate_uf, status in rows:
        name_score = max(fuzz.token_set_ratio(wanted, compact_name(fantasy)), fuzz.token_set_ratio(wanted, compact_name(legal)))
        city_score = fuzz.ratio(city_normalized, normalize(candidate_city)) if city_normalized else 0
        score = name_score + (8 if city_score >= 90 else 0) + (2 if status == "02" else 0)
        if name_score >= 72:
            best.append((score, name_score, city_score, cnpj, fantasy, legal, candidate_city, candidate_uf))
    best.sort(reverse=True)
    if not best:
        return None
    winner = best[0]
    margin = winner[0] - best[1][0] if len(best) > 1 else 100
    strong = winner[1] >= 92 and (not city_normalized or winner[2] >= 85) and margin >= 5
    return {"cnpj": winner[3], "fantasia": winner[4], "razao": winner[5], "cidade": winner[6], "uf": winner[7], "score": winner[1], "margin": margin, "automatic": strong}


def process_sheet(sheet, database_path, progress=print):
    values = sheet.get_all_values()
    if not values:
        raise RuntimeError("A aba da planilha está vazia.")
    headers = values[0]
    required = ["CNPJ", "Endereço", "Cidade", "UF"]
    if any(header not in headers for header in required):
        raise RuntimeError("Aguarde o deploy do sistema criar as colunas CNPJ, Endereço, Cidade e UF.")
    indexes = {name: headers.index(name) for name in headers}
    connection = sqlite3.connect(database_path)
    automatic_updates, review_rows = [], []
    for row_number, original in enumerate(values[1:], 2):
        row = original + [""] * (len(headers) - len(original))
        if row[indexes["CNPJ"]].strip():
            continue
        match = match_lead(connection, row[1], row[indexes["Cidade"]], row[indexes["UF"]], row[2])
        if not match:
            continue
        if match["automatic"]:
            automatic_updates.append({"range": f"N{row_number}", "values": [[re.sub(r'\D', '', match['cnpj'])]]})
        else:
            review_rows.append([row_number, row[1], row[indexes["Cidade"]], row[indexes["UF"]], match["cnpj"], match["fantasia"], match["razao"], match["cidade"], match["uf"], match["score"], match["margin"]])
    if automatic_updates:
        sheet.batch_update(automatic_updates, value_input_option="RAW")
    connection.close()
    progress(f"{len(automatic_updates)} CNPJ(s) gravado(s) automaticamente; {len(review_rows)} para revisão.")
    return automatic_updates, review_rows
