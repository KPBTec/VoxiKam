"use client";
import { useEffect, useState } from "react";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { MessageSquarePlus, Trash2 } from "lucide-react";

interface Comment {
  id: number;
  body: string;
  created_by: string | null;
  created_at: string;
}

export function EntityComments({ entity, entityId }: { entity: "customer" | "carrier"; entityId: number }) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    setComments(await apiGet(`/admin/comments?entity=${entity}&entity_id=${entityId}`));
  }
  useEffect(() => { load() }, [entity, entityId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setSaving(true);
    try {
      await apiPost("/admin/comments", { entity, entity_id: entityId, body });
      setBody("");
      await load();
    } finally { setSaving(false) }
  }

  async function remove(id: number) {
    if (!confirm("¿Eliminar este comentario?")) return;
    await apiDelete(`/admin/comments/${id}`);
    load();
  }

  return (
    <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5 space-y-4">
      <h2 className="font-semibold text-sm flex items-center gap-2">
        <MessageSquarePlus size={15} /> Notas internas
      </h2>

      <form onSubmit={add} className="flex items-end gap-3">
        <textarea
          value={body} onChange={e => setBody(e.target.value)}
          placeholder="Ej: llamé al cliente el 5/7, confirmó pago para mañana..."
          rows={2}
          className="flex-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm resize-none"
        />
        <button type="submit" disabled={saving || !body.trim()}
          className="px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg self-stretch">
          Agregar
        </button>
      </form>

      {comments.length === 0 ? (
        <p className="text-xs text-[var(--color-muted)]">Sin notas todavía</p>
      ) : (
        <div className="space-y-3">
          {comments.map(c => (
            <div key={c.id} className="flex items-start justify-between gap-3 border-b border-[var(--color-border)]/50 pb-3 last:border-0 last:pb-0">
              <div className="min-w-0">
                <p className="text-sm whitespace-pre-wrap break-words">{c.body}</p>
                <p className="text-xs text-[var(--color-muted)] mt-1">
                  {c.created_by ?? "—"} · {new Date(c.created_at).toLocaleString("es-PE")}
                </p>
              </div>
              <button onClick={() => remove(c.id)} aria-label="Eliminar comentario" className="text-[var(--color-muted)] hover:text-red-400 flex-shrink-0">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
