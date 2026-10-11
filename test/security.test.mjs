import { test } from 'node:test';
import assert from 'node:assert/strict';
import { authorize, validMutation } from '../server.mjs';
const config={port:3210,publicHost:'pc.example.ts.net:9443',ownerLogin:'owner@example.com'};
const req=(headers,remote='127.0.0.1')=>({headers,socket:{remoteAddress:remote}});
test('rejects direct LAN traffic even with spoofed identity',()=>assert.equal(authorize(req({host:config.publicHost,'tailscale-user-login':config.ownerLogin},'10.0.0.2'),config),false));
test('requires owner identity through Serve',()=>{
  assert.equal(authorize(req({host:config.publicHost}),config),false);
  assert.equal(authorize(req({host:config.publicHost,'tailscale-user-login':'other@example.com'}),config),false);
  assert.equal(authorize(req({host:config.publicHost,'tailscale-user-login':config.ownerLogin}),config),true);
});
test('rejects DNS rebinding and local-host proxy confusion',()=>{
  assert.equal(authorize(req({host:'evil.example:3210'}),config),false);
  assert.equal(authorize(req({host:'localhost:3210','x-forwarded-for':'10.0.0.2'}),config),false);
  assert.equal(authorize(req({host:'localhost:3210'}),config),true);
});
test('writes require same origin and the bootstrap CSRF secret',()=>{
  assert.equal(validMutation(req({host:config.publicHost,origin:'https://evil.example','x-asia-csrf':'token'}),'token'),false);
  assert.equal(validMutation(req({host:config.publicHost,origin:'https://'+config.publicHost}),'token'),false);
  assert.equal(validMutation(req({host:config.publicHost,origin:'https://'+config.publicHost,'x-asia-csrf':'token'}),'token'),true);
});
