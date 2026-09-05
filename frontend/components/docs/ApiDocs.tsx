"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { DeveloperHeader } from "@/components/developer/DeveloperHeader";

type Example = "curl" | "python" | "javascript" | "compatible";

const API_BASE = "https://inference-api.coreai.uz/v1";
const examples: Record<Example, string> = {
  curl: `curl ${API_BASE}/chat/completions \\
  -H "Authorization: Bearer $COREAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gemma4-31b-it",
    "messages": [
      {"role": "user", "content": "Salom!"}
    ]
  }'`,
  python: `import os
import requests

response = requests.post(
    "${API_BASE}/chat/completions",
    headers={
        "Authorization": f"Bearer {os.environ['COREAI_API_KEY']}",
        "Content-Type": "application/json",
    },
    json={
        "model": "gemma4-31b-it",
        "messages": [{"role": "user", "content": "Salom!"}],
    },
)
response.raise_for_status()
print(response.json()["choices"][0]["message"]["content"])`,
  javascript: `const response = await fetch(
  "${API_BASE}/chat/completions",
  {
    method: "POST",
    headers: {
      Authorization: \`Bearer \${process.env.COREAI_API_KEY}\`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "gemma4-31b-it",
      messages: [{ role: "user", content: "Salom!" }],
    }),
  },
);

if (!response.ok) throw new Error(await response.text());
const result = await response.json();
console.log(result.choices[0].message.content);`,
  compatible: `from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["COREAI_API_KEY"],
    base_url="${API_BASE}",
)

response = client.chat.completions.create(
    model="gemma4-31b-it",
    messages=[{"role": "user", "content": "Salom!"}],
)
print(response.choices[0].message.content)`,
};

const responseExample = `{
  "id": "chatcmpl_...",
  "object": "chat.completion",
  "model": "gemma4-31b-it",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Salom!"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 9,
    "completion_tokens": 4,
    "total_tokens": 13
  }
}`;

const streamExample = `curl -N ${API_BASE}/chat/completions \\
  -H "Authorization: Bearer $COREAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gemma4-31b-it",
    "messages": [{"role": "user", "content": "Salom!"}],
    "stream": true,
    "stream_options": {"include_usage": true}
  }'`;

const reasoningExample = `curl ${API_BASE}/chat/completions \\
  -H "Authorization: Bearer $COREAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "google/gemma-4-31b-it",
    "messages": [{"role": "user", "content": "Compare two deployment plans."}],
    "reasoning": {"enabled": true}
  }'`;

const toolRequestExample = `curl ${API_BASE}/chat/completions \\
  -H "Authorization: Bearer $COREAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "qwen3.8-27b",
    "messages": [{"role": "user", "content": "What is the weather in Tashkent?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city",
        "parameters": {
          "type": "object",
          "properties": {"city": {"type": "string"}},
          "required": ["city"]
        }
      }
    }],
    "tool_choice": "auto"
  }'`;

const toolResponseExample = `{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\\"city\\":\\"Tashkent\\"}"
        }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}`;

const toolResultExample = `{
  "model": "qwen3.8-27b",
  "messages": [
    {"role": "user", "content": "What is the weather in Tashkent?"},
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\\"city\\":\\"Tashkent\\"}"
        }
      }]
    },
    {"role": "tool", "tool_call_id": "call_abc123", "content": "{\\"temperature_c\\":18}"}
  ]
}`;

const parameters = [
  ["model", "string", "docs.required", "docs.paramModel"],
  ["messages", "array", "docs.required", "docs.paramMessages"],
  ["stream", "boolean", "false", "docs.paramStream"],
  ["temperature", "number", "docs.modelDefault", "docs.paramTemperature"],
  ["top_p", "number", "docs.modelDefault", "docs.paramTopP"],
  ["max_tokens", "integer", "docs.modelDefault", "docs.paramMaxTokens"],
  ["stop", "string | array", "null", "docs.paramStop"],
  ["seed", "integer", "null", "docs.paramSeed"],
  ["reasoning", "object", "false", "docs.paramReasoning"],
  ["tools", "array", "null", "docs.paramTools"],
  ["tool_choice", "string | object", "auto / none", "docs.paramToolChoice"],
  ["parallel_tool_calls", "boolean", "true", "docs.paramParallelToolCalls"],
] as const;

export function ApiDocs() {
  const t = useTranslations();
  const [example, setExample] = useState<Example>("curl");
  const [copied, setCopied] = useState<string | null>(null);

  async function copy(id: string, value: string) {
    await navigator.clipboard.writeText(value);
    setCopied(id);
    window.setTimeout(() => setCopied(null), 1600);
  }

  return (
    <main className="min-h-screen bg-page text-fg-primary">
      <DeveloperHeader active="docs" />

      <div className="mx-auto grid max-w-[1180px] lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="sticky top-16 hidden h-[calc(100dvh-64px)] border-r border-line-subtle px-5 py-10 lg:block lg:px-8">
          <div className="mb-3 text-[11px] font-medium uppercase tracking-[0.1em] text-fg-tertiary">{t("docs.contents")}</div>
          <DocsNav />
        </aside>

        <article className="min-w-0 px-5 py-10 md:px-10 lg:px-14 lg:py-14">
          <section className="max-w-3xl">
            <div className="mb-3 text-xs font-medium uppercase tracking-[0.12em] text-orange-hi">{t("docs.eyebrow")}</div>
            <h1 className="m-0 text-4xl font-medium tracking-[-0.03em] md:text-5xl">{t("docs.title")}</h1>
            <p className="mt-5 text-base leading-7 text-fg-secondary md:text-lg">{t("docs.subtitle")}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/console" className="rounded-xl bg-orange px-4 py-2.5 text-sm font-medium text-white no-underline">{t("docs.createKey")}</Link>
              <a href="#quickstart" className="rounded-xl border border-line-strong px-4 py-2.5 text-sm text-fg-primary no-underline">{t("docs.firstRequest")}</a>
            </div>
          </section>

          <section id="overview" className="mt-14 scroll-mt-24">
            <SectionTitle title={t("docs.overviewTitle")} body={t("docs.overviewBody")} />
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <Fact label={t("docs.baseUrl")} value={API_BASE} mono />
              <Fact label={t("docs.auth")} value={t("docs.authValue")} />
              <Fact label={t("docs.formats")} value="JSON · SSE" />
            </div>
          </section>

          <section id="quickstart" className="mt-16 scroll-mt-24">
            <SectionTitle title={t("docs.quickstartTitle")} body={t("docs.quickstartBody")} />
            <ol className="mt-6 grid gap-3 pl-5 text-sm leading-6 text-fg-secondary">
              <li>{t.rich("docs.stepKey", { link: (chunks) => <Link href="/console" className="text-orange-hi">{chunks}</Link> })}</li>
              <li>{t("docs.stepEnv")} <code className="rounded bg-inset px-2 py-1 text-xs text-fg-primary">export COREAI_API_KEY=&quot;cai_...&quot;</code></li>
              <li>{t("docs.stepRequest")}</li>
            </ol>
            <div className="mt-6 overflow-hidden rounded-2xl border border-line-subtle bg-elevated">
              <div className="flex flex-wrap items-center gap-1 border-b border-line-subtle p-2">
                {(["curl", "python", "javascript", "compatible"] as Example[]).map((item) => (
                  <button key={item} onClick={() => setExample(item)} className={`rounded-lg px-3 py-2 text-xs transition-colors ${example === item ? "bg-elevated-2 text-fg-primary" : "text-fg-tertiary hover:text-fg-primary"}`}>{t(`docs.example${item[0].toUpperCase()}${item.slice(1)}`)}</button>
                ))}
              </div>
              <CodeBlock code={examples[example]} copy={() => void copy("quickstart", examples[example])} copied={copied === "quickstart"} t={t} />
            </div>
          </section>

          <section id="authentication" className="mt-16 scroll-mt-24">
            <SectionTitle title={t("docs.authTitle")} body={t("docs.authBody")} />
            <CodeBlock code={'Authorization: Bearer $COREAI_API_KEY\nContent-Type: application/json'} copy={() => void copy("auth", "Authorization: Bearer $COREAI_API_KEY\nContent-Type: application/json")} copied={copied === "auth"} t={t} compact />
            <Callout>{t("docs.secretNote")}</Callout>
          </section>

          <section id="models" className="mt-16 scroll-mt-24">
            <SectionTitle title={t("docs.modelsTitle")} body={t("docs.modelsBody")} />
            <Endpoint method="GET" path="/v1/models" description={t("docs.modelsEndpoint")} />
            <CodeBlock code={`curl ${API_BASE}/models \\\n  -H "Authorization: Bearer $COREAI_API_KEY"`} copy={() => void copy("models", `curl ${API_BASE}/models -H "Authorization: Bearer $COREAI_API_KEY"`)} copied={copied === "models"} t={t} compact />
          </section>

          <section id="chat-completions" className="mt-16 scroll-mt-24">
            <SectionTitle title={t("docs.chatTitle")} body={t("docs.chatBody")} />
            <Endpoint method="POST" path="/v1/chat/completions" description={t("docs.chatEndpoint")} />
            <div className="mt-5 overflow-x-auto rounded-2xl border border-line-subtle">
              <table className="w-full min-w-[680px] border-collapse text-left text-sm">
                <thead className="bg-inset text-xs text-fg-tertiary"><tr><th className="p-3 font-medium">{t("docs.parameter")}</th><th className="p-3 font-medium">{t("docs.type")}</th><th className="p-3 font-medium">{t("docs.default")}</th><th className="p-3 font-medium">{t("docs.description")}</th></tr></thead>
                <tbody>{parameters.map(([name, type, defaultValue, description]) => <tr key={name} className="border-t border-line-subtle"><td className="p-3 font-mono text-xs text-orange-hi">{name}</td><td className="p-3 font-mono text-xs text-fg-secondary">{type}</td><td className="p-3 text-xs text-fg-tertiary">{defaultValue.startsWith("docs.") ? t(defaultValue) : defaultValue}</td><td className="p-3 text-fg-secondary">{t(description)}</td></tr>)}</tbody>
              </table>
            </div>
            <h3 className="mb-3 mt-8 text-base font-medium">{t("docs.responseTitle")}</h3>
            <CodeBlock code={responseExample} copy={() => void copy("response", responseExample)} copied={copied === "response"} t={t} />
          </section>

          <section id="streaming" className="mt-16 scroll-mt-24">
            <SectionTitle title={t("docs.streamingTitle")} body={t("docs.streamingBody")} />
            <CodeBlock code={streamExample} copy={() => void copy("stream", streamExample)} copied={copied === "stream"} t={t} />
            <p className="mt-4 text-sm leading-6 text-fg-secondary">{t("docs.streamingProtocol")}</p>
          </section>

          <section id="reasoning" className="mt-16 scroll-mt-24">
            <SectionTitle title={t("docs.reasoningTitle")} body={t("docs.reasoningBody")} />
            <CodeBlock code={reasoningExample} copy={() => void copy("reasoning", reasoningExample)} copied={copied === "reasoning"} t={t} compact />
            <Callout>{t("docs.reasoningResponse")}</Callout>
          </section>

          <section id="tool-calling" className="mt-16 scroll-mt-24">
            <SectionTitle title={t("docs.toolTitle")} body={t("docs.toolBody")} />
            <h3 className="mb-3 mt-8 text-base font-medium">{t("docs.toolRequestTitle")}</h3>
            <CodeBlock code={toolRequestExample} copy={() => void copy("tool-request", toolRequestExample)} copied={copied === "tool-request"} t={t} />
            <h3 className="mb-3 mt-8 text-base font-medium">{t("docs.toolResponseTitle")}</h3>
            <CodeBlock code={toolResponseExample} copy={() => void copy("tool-response", toolResponseExample)} copied={copied === "tool-response"} t={t} />
            <h3 className="mb-3 mt-8 text-base font-medium">{t("docs.toolResultTitle")}</h3>
            <CodeBlock code={toolResultExample} copy={() => void copy("tool-result", toolResultExample)} copied={copied === "tool-result"} t={t} />
            <Callout>{t("docs.toolResultNote")}</Callout>
            <p className="mt-4 text-sm leading-6 text-fg-secondary">{t("docs.toolStreamNote")}</p>
          </section>

          <section id="data-retention" className="mt-16 scroll-mt-24">
            <SectionTitle title={t("docs.dataTitle")} body={t("docs.dataBody")} />
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <Fact label={t("docs.retentionLabel")} value={t("docs.retentionValue")} />
              <Fact label={t("docs.trainingLabel")} value={t("docs.trainingValue")} />
            </div>
            <p className="mt-4 text-sm leading-6 text-fg-secondary">{t("docs.dataDetail")}</p>
          </section>

          <section id="errors" className="mt-16 scroll-mt-24">
            <SectionTitle title={t("docs.errorsTitle")} body={t("docs.errorsBody")} />
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {[["400", "docs.error400"], ["401", "docs.error401"], ["403", "docs.error403"], ["404", "docs.error404"], ["429", "docs.error429"], ["503", "docs.error503"]].map(([code, key]) => <div key={code} className="flex gap-4 rounded-xl border border-line-subtle bg-elevated p-4"><code className="text-orange-hi">{code}</code><span className="text-sm text-fg-secondary">{t(key)}</span></div>)}
            </div>
            <p className="mt-5 text-sm leading-6 text-fg-secondary">{t("docs.rateHeaders")}</p>
          </section>

          <div className="h-16" />
        </article>
      </div>
    </main>
  );
}

function DocsNav() {
  const t = useTranslations("docs");
  const links = [["overview", "overviewTitle"], ["quickstart", "quickstartTitle"], ["authentication", "authTitle"], ["models", "modelsTitle"], ["chat-completions", "chatTitle"], ["streaming", "streamingTitle"], ["reasoning", "reasoningTitle"], ["tool-calling", "toolTitle"], ["data-retention", "dataTitle"], ["errors", "errorsTitle"]];
  return <nav className="flex flex-col gap-1">{links.map(([id, key]) => <a key={id} href={`#${id}`} className="rounded-lg px-3 py-2 text-sm text-fg-secondary no-underline hover:bg-elevated hover:text-fg-primary">{t(key)}</a>)}</nav>;
}

function SectionTitle({ title, body }: { title: string; body: string }) {
  return <div className="max-w-3xl"><h2 className="m-0 text-2xl font-medium tracking-tight md:text-3xl">{title}</h2><p className="mb-0 mt-3 text-sm leading-7 text-fg-secondary md:text-base">{body}</p></div>;
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="rounded-xl border border-line-subtle bg-elevated p-4"><div className="text-xs text-fg-tertiary">{label}</div><div className={`mt-2 text-sm leading-6 text-fg-primary ${mono ? "break-all font-mono text-xs" : ""}`}>{value}</div></div>;
}

function Callout({ children }: { children: React.ReactNode }) {
  return <div className="mt-5 rounded-xl border border-orange/25 bg-orange-tint px-4 py-3 text-sm leading-6 text-fg-secondary">{children}</div>;
}

function Endpoint({ method, path, description }: { method: string; path: string; description: string }) {
  return <div className="mt-5 flex flex-col gap-3 rounded-xl border border-line-subtle bg-elevated p-4 sm:flex-row sm:items-center"><span className="w-fit rounded-md bg-orange-tint px-2 py-1 font-mono text-xs font-medium text-orange-hi">{method}</span><code className="text-sm text-fg-primary">{path}</code><span className="text-sm text-fg-secondary sm:ml-auto">{description}</span></div>;
}

function CodeBlock({ code, copy, copied, t, compact = false }: { code: string; copy: () => void; copied: boolean; t: ReturnType<typeof useTranslations>; compact?: boolean }) {
  return <div className={`relative overflow-hidden rounded-2xl border border-line-subtle bg-inset ${compact ? "mt-5" : ""}`}><button onClick={copy} className="absolute right-3 top-3 z-10 rounded-md border border-line-default bg-elevated px-2.5 py-1.5 text-[11px] text-fg-secondary hover:text-fg-primary">{copied ? t("common.copied") : t("common.copy")}</button><pre className="ca-scroll m-0 overflow-x-auto p-5 pr-20 font-mono text-xs leading-6 text-fg-secondary"><code>{code}</code></pre></div>;
}
