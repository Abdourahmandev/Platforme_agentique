import test from 'node:test';
import assert from 'node:assert/strict';
import {classifyTask} from '../infra/task-outcome.mjs';

test('perte de transport apres acceptation : unknown et non relancable', () => {
  assert.deepEqual(classifyTask({accepted: true, transportLost: true}),
    {state: 'unknown', retrySafe: false});
});

test('rejet explicite avant acceptation : relancable', () => {
  assert.deepEqual(classifyTask({accepted: false, terminal: 'rejected'}),
    {state: 'rejected', retrySafe: true});
});

test('rejonction contradictoire : rejet apres acceptation -> unknown', () => {
  // Contradiction : accepted affirme true alors que terminal vaut rejected.
  // Le contrat prime : rejected n'est valide que si accepted === false.
  assert.deepEqual(classifyTask({accepted: true, terminal: 'rejected'}),
    {state: 'unknown', retrySafe: false});
});

// Regression : l'erreur initiale relancait une tache sur simple perte de
// transport AVANT tout accuse. Le pair a peut-etre deja execute la mutation ;
// cette issue reste donc inconnue et non relancable.
test('perte de transport avant acceptation : unknown et NON relancable (regression)', () => {
  assert.deepEqual(classifyTask({accepted: false, transportLost: true}),
    {state: 'unknown', retrySafe: false});
});

test('perte de transport avec accepted absent : unknown et NON relancable (regression)', () => {
  assert.deepEqual(classifyTask({transportLost: true}),
    {state: 'unknown', retrySafe: false});
});

test('rejet avant acceptation mais accepted non booleen : pas de relance', () => {
  for (const accepted of [null, 'false', 0, '', undefined]) {
    const out = classifyTask({accepted, terminal: 'rejected'});
    assert.equal(out.state, 'unknown', 'accepted=' + String(accepted));
    assert.equal(out.retrySafe, false, 'accepted=' + String(accepted));
  }
});

test('rejet avec accepted true contradictoire : unknown sans relance', () => {
  assert.deepEqual(classifyTask({accepted: true, terminal: 'rejected'}),
    {state: 'unknown', retrySafe: false});
});

test('terminal timed_out : unknown et NON relancable', () => {
  assert.deepEqual(classifyTask({accepted: false, terminal: 'timed_out'}),
    {state: 'unknown', retrySafe: false});
  assert.deepEqual(classifyTask({accepted: true, terminal: 'timed_out'}),
    {state: 'unknown', retrySafe: false});
});

test('issue terminale explicite avant toute perte de transport', () => {
  assert.deepEqual(classifyTask({accepted: true, transportLost: true, terminal: 'succeeded'}),
    {state: 'succeeded', retrySafe: false});
});

test('etats terminaux defavorables : jamais relances automatiquement', () => {
  assert.deepEqual(classifyTask({accepted: true, terminal: 'failed'}),
    {state: 'failed', retrySafe: false});
  assert.deepEqual(classifyTask({accepted: false, terminal: 'failed'}),
    {state: 'failed', retrySafe: false});
  assert.deepEqual(classifyTask({accepted: true, terminal: 'cancelled'}),
    {state: 'cancelled', retrySafe: false});
});

// Regressions finales : une issue terminale confirmee prime sur la perte de
// transport, y compris quand les deux sont presents.
test('terminal confirme avec transportLost true : issue terminale respectee', () => {
  assert.deepEqual(classifyTask({accepted: true, transportLost: true, terminal: 'succeeded'}),
    {state: 'succeeded', retrySafe: false});
  assert.deepEqual(classifyTask({accepted: true, transportLost: true, terminal: 'failed'}),
    {state: 'failed', retrySafe: false});
  assert.deepEqual(classifyTask({accepted: true, transportLost: true, terminal: 'cancelled'}),
    {state: 'cancelled', retrySafe: false});
  // Sans acceptation explicite, un terminal favorable reste sans relance ;
  // un rejet non confirme retombe sur unknown.
  assert.deepEqual(classifyTask({accepted: false, transportLost: true, terminal: 'succeeded'}),
    {state: 'succeeded', retrySafe: false});
  assert.deepEqual(classifyTask({transportLost: true, terminal: 'rejected'}),
    {state: 'unknown', retrySafe: false});
});

test('tache acceptee sans retour : pending, non relancable', () => {
  assert.deepEqual(classifyTask({accepted: true}),
    {state: 'pending', retrySafe: false});
});

test('tache acceptee sans retour : pending, non relancable', () => {
  assert.deepEqual(classifyTask({accepted: true}),
    {state: 'pending', retrySafe: false});
});

// Correction de contrat : "pending" exige accepted === true ET aucune issue
// terminale ET aucune perte de transport. Sans acceptation confirmee, l'etat
// reel reste inconnu. L'ancien test attendait "pending" pour une entree vide ou
// non acceptee, ce qui contredisait ce contrat ; il est corrige ici, sans
// supprimer ni affaiblir les autres assertions.
test('tache non acceptee ou entree vide : unknown, jamais pending ni relancable', () => {
  assert.deepEqual(classifyTask({}),
    {state: 'unknown', retrySafe: false});
  assert.deepEqual(classifyTask({accepted: false, transportLost: false, terminal: null}),
    {state: 'unknown', retrySafe: false});
  assert.deepEqual(classifyTask({accepted: false}),
    {state: 'unknown', retrySafe: false});
});

test('valeur terminale inconnue : prudence maximale', () => {
  assert.deepEqual(classifyTask({accepted: false, terminal: 'bizarre'}),
    {state: 'unknown', retrySafe: false});
});

test('booleens non stricts : jamais coercition en false, resultat unknown', () => {
  for (const transportLost of [null, 'true', 1, 'false']) {
    const out = classifyTask({accepted: false, transportLost});
    assert.equal(out.state, 'unknown', 'transportLost=' + String(transportLost));
    assert.equal(out.retrySafe, false, 'transportLost=' + String(transportLost));
  }
});

test('entree manquante ou non objet : unknown sans relance', () => {
  for (const input of [undefined, null, 'rejected', 42, []]) {
    const out = classifyTask(input);
    assert.equal(out.state, 'unknown');
    assert.equal(out.retrySafe, false);
  }
});

test('sortie toujours limitee aux etats prevus et booleens', () => {
  const states = new Set(['pending', 'succeeded', 'failed', 'cancelled', 'unknown', 'rejected']);
  for (const accepted of [true, false]) {
    for (const transportLost of [true, false]) {
      for (const terminal of [null, 'succeeded', 'failed', 'cancelled', 'rejected', 'timed_out']) {
        const {state, retrySafe} = classifyTask({accepted, transportLost, terminal});
        assert.ok(states.has(state), 'etat inattendu: ' + state);
        assert.equal(typeof retrySafe, 'boolean');
      }
    }
  }
});

// Objet gele : classifyTask ne doit ni muter l'entree ni autoriser une
// relance quand accepted=true, terminal=cancelled et transportLost=true.
// Un gele (Object.freeze) fait echouer toute ecriture en mode strict : le test
// prouve l'absence de mutation, la lecture correcte et retrySafe=false.
test('objet gele accepted=true/terminal cancelled/transportLost=true : lu sans mutation ni relance', () => {
  const input = Object.freeze({
    accepted: true,
    terminal: 'cancelled',
    transportLost: true,
  });
  const result = classifyTask(input);
  assert.deepEqual(result, {state: 'cancelled', retrySafe: false});
  assert.ok(Object.isFrozen(input));
  assert.deepEqual(input, {accepted: true, terminal: 'cancelled', transportLost: true});
  // Second appel : confirme qu'aucun etat cache n'a ete introduit dans l'entree.
  assert.deepEqual(classifyTask(input), {state: 'cancelled', retrySafe: false});
});

test('aucune entree incertaine ne rend retrySafe true sans rejet confirme', () => {
  const inputs = [
    {}, {accepted: true}, {transportLost: true}, {accepted: true, transportLost: true},
    {accepted: null, terminal: 'rejected'}, {accepted: 'false', terminal: 'rejected'},
    {terminal: 'timed_out'}, {terminal: 'bizarre'}, {transportLost: true, terminal: 'failed'}
  ];
  for (const input of inputs) {
    assert.equal(classifyTask(input).retrySafe, false, JSON.stringify(input));
  }
  assert.equal(classifyTask({accepted: false, terminal: 'rejected'}).retrySafe, true);
});
