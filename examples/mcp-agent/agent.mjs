// The upstream 1.1.1 package publishes extensionless ESM imports. Register tsx's
// resolver, then import its real Agent implementation rather than copying it.
import { register } from 'tsx/esm/api';
import { createInterface } from 'node:readline';
import net from 'node:net';
import tls from 'node:tls';
import { FixtureLLM } from './fixture-llm.mjs';

// Fail accidental live SDK/tracing requests in this fixture-only example. This
// is a test assertion on Node networking, not a general security sandbox.
const rejectNetwork = () => { throw new Error('Unexpected network request in replay example'); };
net.Socket.prototype.connect = rejectNetwork;
tls.connect = rejectNetwork;
globalThis.fetch = rejectNetwork;

function denied(operation) {
  try { operation(); } catch (error) {
    return error.message === 'Unexpected network request in replay example';
  }
  return false;
}
const networkGuard = {
  fetch_blocked: denied(() => fetch('http://127.0.0.1:9')),
  socket_blocked: denied(() => new net.Socket().connect(9, '127.0.0.1')),
  tls_blocked: denied(() => tls.connect({ host: '127.0.0.1', port: 9 })),
};
if (!Object.values(networkGuard).every(Boolean)) throw new Error('Replay network guard failed');

register();
const { Agent, Logger, LogLevel, SimpleMemory } = await import('@joshuacalpuerto/mcp-agent');

const scenario = process.argv[2] || 'pass';
const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
const pending = new Map();
let nextCall = 0;
let started = false;

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function requestTool(name, args) {
  return new Promise((resolve, reject) => {
    const callId = `tool-${++nextCall}`;
    const timer = setTimeout(() => {
      pending.delete(callId);
      reject(new Error(`No RunLedger result for ${callId}`));
    }, 15000);
    pending.set(callId, { resolve, reject, timer });
    send({ type: 'tool_call', name, call_id: callId, args });
  });
}

const stderrLogger = Object.fromEntries(
  ['info', 'warn', 'debug', 'error'].map((level) => [level, (message) => {
    process.stderr.write(`${message}\n`);
  }]),
);
const logger = Logger.getInstance(stderrLogger, { level: LogLevel.ERROR });

async function runTask(task) {
  send({ type: 'log', level: 'info', message: 'Replay network guard verified', data: networkGuard });
  // Registered functions keep upstream Agent.callTool() intact. Only the actual
  // external operation crosses RunLedger's protocol boundary.
  const functions = [
    {
      name: 'search_docs',
      description: 'Find support documentation for a question',
      parameters: {
        type: 'object', properties: { q: { type: 'string' } }, required: ['q'],
      },
      execute: (args) => requestTool('search_docs', args),
    },
    {
      name: 'read_doc',
      description: 'Read a documentation page by identifier',
      parameters: {
        type: 'object', properties: { id: { type: 'string' } }, required: ['id'],
      },
      execute: (args) => requestTool('read_doc', args),
    },
  ];
  const agent = new Agent({
    name: 'support-documentation',
    description: 'Answer a support question using search_docs and read_doc.',
    llm: new FixtureLLM(scenario),
    functions,
    history: new SimpleMemory(),
    logger,
    maxIterations: 5,
  });
  agent.onAgentEvent((event) => {
    send({
      type: 'log', level: 'debug', message: 'upstream Agent lifecycle',
      data: { action: event.action, tool: event.metadata?.toolName ?? null },
    });
  });
  try {
    // Executes the published Agent.generate loop, listTools, callTool, memory,
    // lifecycle events, and final JSON parsing. None are replaced by this adapter.
    return await agent.generateStructuredResult(task.input.prompt);
  } finally {
    await agent.close();
  }
}

function finish(error) {
  for (const item of pending.values()) clearTimeout(item.timer);
  pending.clear();
  if (error) {
    send({ type: 'task_error', message: String(error.message || error) });
    process.exitCode = 1;
  }
  input.close();
  process.stdin.pause();
}

input.on('line', (line) => {
  try {
    const message = JSON.parse(line);
    if (message.type === 'tool_result') {
      const item = pending.get(message.call_id);
      if (!item) throw new Error(`Unexpected tool result ${message.call_id}`);
      pending.delete(message.call_id);
      clearTimeout(item.timer);
      if (message.ok) {
        // mcp-agent consumes MCP-shaped content; the cassette stores the tool's
        // domain result, and this thin bridge supplies the MCP text envelope.
        item.resolve({ content: [{ type: 'text', text: JSON.stringify(message.result) }] });
      } else {
        item.reject(new Error(message.error || 'Tool failed'));
      }
    } else if (message.type === 'task_start' && !started) {
      started = true;
      runTask(message).then((output) => {
        send({ type: 'final_output', output });
        finish();
      }).catch(finish);
    } else {
      throw new Error(`Unexpected protocol message ${message.type}`);
    }
  } catch (error) {
    finish(error);
  }
});
