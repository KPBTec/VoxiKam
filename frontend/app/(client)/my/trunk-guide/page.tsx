"use client";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

export default function TrunkGuide() {
  const [data, setData] = useState<any>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => { apiGet("/my/trunk-guide").then(setData); }, []);

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopied(key); setTimeout(() => setCopied(null), 2000);
  };

  if (!data) return <div className="text-[var(--color-muted)] p-8">Cargando...</div>;

  const CodeBlock = ({ code, id }: { code: string; id: string }) => (
    <div className="relative">
      <pre className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-4
                      text-xs text-green-300 font-mono overflow-x-auto">{code}</pre>
      <button onClick={() => copy(code, id)}
        className="absolute top-2 right-2 text-xs text-[var(--color-muted)] hover:text-brand-400
                   bg-[var(--color-card)] px-2 py-1 rounded border border-[var(--color-border)] transition-colors">
        {copied === id ? "Copiado!" : "Copiar"}
      </button>
    </div>
  );

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold">Guía de configuración Trunk</h1>

      <div className="bg-[var(--color-card)] border border-brand-600/40 rounded-xl p-6 space-y-2">
        <h2 className="font-semibold text-brand-400 mb-3">Tus datos de acceso</h2>
        {[
          ["Host SBC",     data.sbc_host],
          ["Puerto",       data.sbc_port],
          ["Autenticación","IP (no requiere usuario/contraseña)"],
          ["Tu prefijo",   data.prefix],
        ].map(([label, val]) => (
          <div key={label} className="flex justify-between text-sm py-1 border-b border-[var(--color-border)]/30">
            <span className="text-[var(--color-text-2)]">{label}</span>
            <span className="font-mono text-[var(--color-text)]">{val}</span>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        <h2 className="font-semibold">1. sip.conf — configuración del trunk</h2>
        <CodeBlock code={data.sip_conf} id="sip_conf" />
      </div>

      <div className="space-y-3">
        <h2 className="font-semibold">2. extensions.conf — dialplan base</h2>
        <CodeBlock code={data.dialplan} id="dialplan" />
      </div>

      <div className="bg-yellow-900/20 border border-yellow-700/40 rounded-xl p-5 text-sm space-y-2">
        <p className="font-semibold text-yellow-400">Importante</p>
        <ul className="text-[var(--color-text-2)] space-y-1 list-disc list-inside">
          <li>Tu prefijo <span className="font-mono text-brand-400">{data.prefix}</span> debe incluirse en CADA llamada saliente.</li>
          <li>Asegúrate de que tu IP pública esté registrada en el panel.</li>
          <li>El SBC solo acepta INVITEs desde IPs autorizadas.</li>
          <li>Códecs soportados: G.711 ulaw/alaw, G.729.</li>
        </ul>
      </div>
    </div>
  );
}
