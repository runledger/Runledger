import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/model-responses.json', import.meta.url), 'utf8'));

// An explicitly authored model fixture, not a live model and not a recording of
// a production model run. It exercises the real Agent's orchestration mechanics.
export class FixtureLLM {
  constructor(scenario) {
    assert.ok(['pass', 'missing-field', 'wrong-order', 'extra-tool'].includes(scenario));
    this.scenario = scenario;
    this.turn = 0;
    this.calls = structuredClone(fixture.toolDecisions);
    if (scenario === 'wrong-order') this.calls.reverse();
    if (scenario === 'extra-tool') this.calls.push(structuredClone(this.calls[0]));
  }

  async generate({ messages, config }) {
    const toolMessages = messages.filter((message) => message.role === 'tool');
    // Verify that upstream Agent fed the bridged tool results back into the
    // next model turn. A disconnected/fake tool path cannot satisfy this check.
    assert.equal(toolMessages.length, this.turn);
    for (let index = 0; index < toolMessages.length; index += 1) {
      const envelope = JSON.parse(toolMessages[index].content);
      const result = JSON.parse(envelope.content[0].text);
      assert.deepEqual(result, fixture.expectedResults[this.calls[index].name]);
    }
    assert.equal(messages.find((message) => message.role === 'user')?.content, fixture.prompt);

    const decision = this.calls[this.turn];
    if (decision) {
      assert.ok(config.tools.some((tool) => tool.function.name === decision.name));
      this.turn += 1;
      return {
        content: null,
        finishReason: 'tool_calls',
        toolCalls: [{
          id: `model-call-${this.turn}`, type: 'function',
          function: { name: decision.name, arguments: JSON.stringify(decision.args) },
        }],
      };
    }
    const output = structuredClone(fixture.finalOutput);
    if (this.scenario === 'missing-field') delete output.reply;
    return { content: JSON.stringify(output), toolCalls: [], finishReason: 'stop' };
  }
}
