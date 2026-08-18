// Real-server compatibility smoke test using the official OpenAI JavaScript SDK.

import OpenAI from "openai";

function required(name) {
  const value = (process.env[name] || "").trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const baseURL = (process.env.COREAI_BASE_URL || "http://localhost:8008/v1").replace(/\/$/, "");
const model = required("COREAI_MODEL");
const client = new OpenAI({
  apiKey: required("COREAI_API_KEY"),
  baseURL,
  maxRetries: 0,
  timeout: 45_000,
});

const models = await client.models.list();
const modelIds = models.data.map((item) => item.id);
if (!modelIds.includes(model)) {
  throw new Error(`${JSON.stringify(model)} not present in /models: ${JSON.stringify(modelIds)}`);
}

const completion = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: "Reply with exactly: JAVASCRIPT SDK OK" }],
  temperature: 0,
  max_tokens: 32,
});
if (!completion.choices[0]?.message?.content?.trim()) {
  throw new Error("non-streaming completion returned empty content");
}
if (!completion.usage || completion.usage.total_tokens <= 0) {
  throw new Error("non-streaming completion returned no usage");
}

const stream = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: "Reply with exactly: JAVASCRIPT STREAM OK" }],
  temperature: 0,
  max_tokens: 32,
  stream: true,
  stream_options: { include_usage: true },
});
const pieces = [];
let streamUsage = null;
for await (const chunk of stream) {
  if (chunk.choices[0]?.delta?.content) pieces.push(chunk.choices[0].delta.content);
  if (chunk.usage) streamUsage = chunk.usage;
}
if (!pieces.join("").trim()) throw new Error("streaming completion returned empty content");
if (!streamUsage || streamUsage.total_tokens <= 0) {
  throw new Error("streaming completion returned no terminal usage");
}

console.log(JSON.stringify({
  sdk: "javascript",
  status: "ok",
  base_url: baseURL,
  model,
  models: modelIds,
  nonstream_tokens: completion.usage.total_tokens,
  stream_tokens: streamUsage.total_tokens,
}));
