export function createCrmApi(baseUrl) {
  return async function crmApi(path, options = {}) {
    const isRead = !options.method || options.method === "GET";
    const separator = path.includes("?") ? "&" : "?";
    const requestPath = isRead ? `${path}${separator}_=${Date.now()}` : path;
    const response = await fetch(`${baseUrl}${requestPath}`, {
      ...options,
      cache: isRead ? "no-store" : undefined,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(typeof body.detail === "string" ? body.detail : "Não foi possível concluir a operação.");
    }
    return body;
  };
}

