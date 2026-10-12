import {test} from 'node:test';
import assert from 'node:assert/strict';
import {GatewayClient} from '../infra/gateway-client.mjs';

test('Gateway timeouts preserve uncertainty and never replay a mutation',async()=>{
  const c=new GatewayClient({url:'ws://127.0.0.1:18789',token:'test',device:{}});
  let sent=0;c.socket={send(){sent++;}};
  await assert.rejects(c.request('chat.send',{},10),e=>{
    assert.deepEqual(e.outcome,{state:'unknown',retrySafe:false});return true;
  });
  assert.equal(sent,1);assert.equal(c.pending.size,0);
});

test('Gateway send failure cannot be interpreted as permission to retry',async()=>{
  const c=new GatewayClient({url:'ws://127.0.0.1:18789',token:'test',device:{}});
  let sent=0;c.socket={send(){sent++;throw Error('internal transport details');}};
  await assert.rejects(c.request('chat.send'),e=>{
    assert.deepEqual(e.outcome,{state:'unknown',retrySafe:false});
    assert.equal(e.message.includes('internal transport details'),false);return true;
  });
  assert.equal(sent,1);assert.equal(c.pending.size,0);
});
