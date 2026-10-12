// Classification de l'issue d'une tache deleguee, sans dependance externe.
//
// Regle de base : ne jamais relancer une mutation dont l'issue est incertaine.
// Une perte de transport avant reception d'un accuse ne prouve pas que le pair
// n'a rien execute : elle ne rend donc jamais une relance sure. Seul un rejet
// explicite confirme avant acceptation est surement sans effet.
//
// Entree : {accepted, terminal, transportLost}
//   - accepted      : booleen strict. La tache a ete acceptee par le pair (au
//                     moins la prise en charge a ete confirmee). null, une
//                     chaine ou toute autre valeur non booleenne est invalide.
//   - terminal      : issue explicite recue, parmi
//                     'succeeded' | 'failed' | 'cancelled' | 'rejected',
//                     sinon null/undefined. 'timed_out' est un echec de
//                     transport, pas une issue terminale confirmee.
//   - transportLost : booleen strict. La connexion a ete perdue sans issue
//                     terminale connue.
//
// Sortie : {state, retrySafe}
//   - state     : pending | succeeded | failed | cancelled | unknown | rejected
//   - retrySafe : true uniquement si une nouvelle tentative est sure.

const CONFIRMED_TERMINAL = new Set(['succeeded', 'failed', 'cancelled', 'rejected']);
const TIMEOUT_TERMINAL = 'timed_out';

function isStrictBoolean(value) {
  return typeof value === 'boolean';
}

export function classifyTask(input) {
  // Un objet manquant, non objet ou vide ne permet aucune conclusion : on ne
  // suppose jamais un succes ni une permission de relancer.
  if (input == null || typeof input !== 'object' || Array.isArray(input)) {
    return {state: 'unknown', retrySafe: false};
  }

  const {accepted, terminal, transportLost} = input;

  // Booleens valides sans coercition : null, undefined, une chaine ou tout
  // autre type ne vaut ni true ni false lorsqu'il est present.
  const acceptedValid = accepted === undefined || isStrictBoolean(accepted);
  const transportLostValid = transportLost === undefined || isStrictBoolean(transportLost);
  if (!acceptedValid || !transportLostValid) {
    return {state: 'unknown', retrySafe: false};
  }

  const transportLostBool = transportLost === true;

  const terminalRaw = terminal == null ? null : terminal;
  if (terminalRaw !== null && typeof terminalRaw !== 'string') {
    return {state: 'unknown', retrySafe: false};
  }

  // Une issue terminale confirmee prime sur toute perte de transport : l'ordre
  // des evenements est deja tranche.
  if (terminalRaw !== null && CONFIRMED_TERMINAL.has(terminalRaw)) {
    // Un rejet n'est sur que s'il est explicitement recue avant acceptation :
    // accepted === false doit etre un booleen explicite et present. Une valeur
    // absente, nulle ou d'un autre type est contradictoire ou manquante et
    // retombe sur unknown, sans relance.
    if (terminalRaw === 'rejected' && accepted !== false) {
      return {state: 'unknown', retrySafe: false};
    }
    const retrySafe = terminalRaw === 'rejected';
    return {state: terminalRaw, retrySafe};
  }

  // Un delai depasse cote terminal n'est pas une issue confirmee : il equivaut
  // a une perte de transport et ne permet jamais une relance sure.
  // Toute autre valeur terminale contradictoire ou invalide : meme prudence.
  if (terminalRaw !== null) {
    return {state: 'unknown', retrySafe: false};
  }

  // Perte de transport (panne ou timed_out) sans issue terminale confirmee :
  // le pair a peut-etre execute quelque chose. Jamais de relance sure.
  if (transportLostBool) {
    return {state: 'unknown', retrySafe: false};
  }

  // Une tache n'est "pending" que si son acceptation est explicitement
  // confirmee (accepted === true). Sans cette confirmation, l'etat reel est
  // inconnu : on ne suppose ni acceptation ni succes.
  if (accepted === true) {
    return {state: 'pending', retrySafe: false};
  }
  return {state: 'unknown', retrySafe: false};
}

export default classifyTask;
