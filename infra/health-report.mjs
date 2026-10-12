// Assess the health of an installation snapshot.
//
// Pure: no dependency, no I/O, no mutation of the input. The output never
// echoes raw input or extra fields, only a status and explicit issue texts.
//
// Status precedence: "degraded" beats "unknown" beats "ok".

const STATUS = { OK: 'ok', DEGRADED: 'degraded', UNKNOWN: 'unknown' };
const RANK = { degraded: 2, unknown: 1, ok: 0 };

// A field is usable only when it is a non-empty string.
function usableText(value) {
  return typeof value === 'string' && value.trim() !== '';
}

// Strict boolean: null, undefined and strings do not count as a boolean.
function isBoolean(value) {
  return typeof value === 'boolean';
}

export function assessHealth(input) {
  const issues = [];
  let status = STATUS.OK;

  const raise = (candidate, message) => {
    issues.push(message);
    if (RANK[candidate] > RANK[status]) status = candidate;
  };

  const record = input && typeof input === 'object' && !Array.isArray(input) ? input : null;

  // --- services -----------------------------------------------------------
  const services = record ? record.services : undefined;
  if (!Array.isArray(services) || services.length === 0) {
    raise(STATUS.UNKNOWN, 'services: aucun service fourni; etat inconnu');
  } else {
    services.forEach((service, index) => {
      // Ne jamais recopier service.name : cette chaine vient d'une source
      // externe et pourrait transporter du texte arbitraire (secret, HTML).
      // On identifie le service par sa position pour un message stable.
      const label = `services[${index}]`;
      const healthy = service && typeof service === 'object' ? service.healthy : undefined;
      if (!isBoolean(healthy)) {
        raise(STATUS.UNKNOWN, `service ${label}: etat de sante absent ou invalide; etat inconnu`);
      } else if (healthy === false) {
        raise(STATUS.DEGRADED, `service ${label}: signale non sain`);
      }
    });
  }

  // --- backup -------------------------------------------------------------
  const backup = record ? record.backup : undefined;
  if (!backup || typeof backup !== 'object' || Array.isArray(backup)) {
    raise(STATUS.UNKNOWN, 'backup: informations de sauvegarde absentes; etat inconnu');
  } else {
    if (!isBoolean(backup.verified)) {
      raise(STATUS.UNKNOWN, 'backup: verification absente ou invalide; etat inconnu');
    } else if (backup.verified === false) {
      raise(STATUS.DEGRADED, 'backup: sauvegarde non verifiee');
    }

    const age = backup.ageHours;
    if (age === undefined || age === null) {
      raise(STATUS.UNKNOWN, 'backup: age de la sauvegarde absent; etat inconnu');
    } else if (typeof age !== 'number' || !Number.isFinite(age) || age < 0) {
      raise(STATUS.UNKNOWN, 'backup: age de la sauvegarde invalide; etat inconnu');
    } else if (age > 26) {
      raise(STATUS.DEGRADED, `backup: sauvegarde trop ancienne (${age} h > 26 h)`);
    }
  }

  // --- delegation ---------------------------------------------------------
  const delegation = record ? record.delegation : undefined;
  if (!delegation || typeof delegation !== 'object' || Array.isArray(delegation)) {
    raise(STATUS.UNKNOWN, 'delegation: informations de delegation absentes; etat inconnu');
  } else {
    const state = delegation.state;
    if (!usableText(state)) {
      raise(STATUS.UNKNOWN, 'delegation: etat absent ou invalide; etat inconnu');
    } else if (state === 'succeeded') {
      // nominal, nothing to add
    } else if (state === 'failed' || state === 'cancelled') {
      raise(STATUS.DEGRADED, `delegation: mission ${state}`);
    } else {
      // Un etat non reconnu ne doit pas etre recopie : il vient d'une source
      // externe. On signale un etat inconnu avec un message generique.
      raise(STATUS.UNKNOWN, 'delegation: etat non reconnu; etat inconnu');
    }
  }

  return { status, issues };
}
