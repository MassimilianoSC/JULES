/**
 * Simple JavaScript Logger
 *
 * livelli di Log: DEBUG, INFO, WARN, ERROR, NONE
 *
 * Uso:
 * import logger from './logger.js';
 * logger.setLogLevel(logger.levels.DEBUG); // Imposta il livello (opzionale, default INFO)
 *
 * logger.debug('Messaggio di debug', { dati });
 * logger.info('Informazione utile');
 * logger.warn('Attenzione, qualcosa di strano');
 * logger.error('Errore!', new Error('dettagli errore'));
 */

const levels = {
    DEBUG: 0,
    INFO: 1,
    WARN: 2,
    ERROR: 3,
    NONE: 4,
};

let currentLogLevel = levels.INFO; // Livello di default

function setLogLevel(level) {
    if (typeof level === 'string' && levels[level.toUpperCase()] !== undefined) {
        currentLogLevel = levels[level.toUpperCase()];
    } else if (typeof level === 'number' && Object.values(levels).includes(level)) {
        currentLogLevel = level;
    } else {
        console.warn(`[Logger] Livello di log non valido: ${level}. Mantengo ${Object.keys(levels).find(key => levels[key] === currentLogLevel)}.`);
    }
}

function getTimestamp() {
    return new Date().toISOString();
}

function formatMessage(levelName, moduleName = 'App', ...args) {
    const timestamp = getTimestamp();
    let message = `${timestamp} [${levelName}]`;
    if (moduleName) {
        message += ` [${moduleName}]`;
    }

    const MASK_PASSWORD_REGEX = /("?(?:password|token|secret)"?\s*:\s*")[^"]*(")/gi;

    const processedArgs = args.map(arg => {
        if (typeof arg === 'string') {
            // Maschera password nelle stringhe JSON-like
            return arg.replace(MASK_PASSWORD_REGEX, '$1********$2');
        }
        if (typeof arg === 'object' && arg !== null) {
            try {
                // Maschera password negli oggetti (convertendo temporaneamente a JSON)
                let strArg = JSON.stringify(arg);
                strArg = strArg.replace(MASK_PASSWORD_REGEX, '$1********$2');
                return JSON.parse(strArg);
            } catch (e) {
                return arg; // Lascia l'oggetto così com'è se non è serializzabile/deserializzabile
            }
        }
        return arg;
    });


    return [message, ...processedArgs];
}

const logger = {
    levels,
    setLogLevel,

    debug: (moduleOrMessage, ...args) => {
        if (currentLogLevel <= levels.DEBUG) {
            const moduleName = typeof moduleOrMessage === 'string' && args.length > 0 ? moduleOrMessage : null;
            const messageArgs = moduleName ? args : [moduleOrMessage, ...args];
            console.debug(...formatMessage('DEBUG', moduleName, ...messageArgs));
        }
    },
    info: (moduleOrMessage, ...args) => {
        if (currentLogLevel <= levels.INFO) {
            const moduleName = typeof moduleOrMessage === 'string' && args.length > 0 ? moduleOrMessage : null;
            const messageArgs = moduleName ? args : [moduleOrMessage, ...args];
            console.info(...formatMessage('INFO', moduleName, ...messageArgs));
        }
    },
    warn: (moduleOrMessage, ...args) => {
        if (currentLogLevel <= levels.WARN) {
            const moduleName = typeof moduleOrMessage === 'string' && args.length > 0 ? moduleOrMessage : null;
            const messageArgs = moduleName ? args : [moduleOrMessage, ...args];
            console.warn(...formatMessage('WARN', moduleName, ...messageArgs));
        }
    },
    error: (moduleOrMessage, ...args) => {
        if (currentLogLevel <= levels.ERROR) {
            const moduleName = typeof moduleOrMessage === 'string' && args.length > 0 ? moduleOrMessage : null;
            const messageArgs = moduleName ? args : [moduleOrMessage, ...args];
            console.error(...formatMessage('ERROR', moduleName, ...messageArgs));
        }
    },
    // Permette di passare il nome del modulo come primo argomento opzionale
    // Esempio: log('MyModule').info('Messaggio');
    module: function(moduleName) {
        return {
            debug: (...args) => logger.debug(moduleName, ...args),
            info:  (...args) => logger.info(moduleName, ...args),
            warn:  (...args) => logger.warn(moduleName, ...args),
            error: (...args) => logger.error(moduleName, ...args),
        };
    }
};

// Impostazione di default per lo sviluppo
// In un ambiente di produzione, questo potrebbe essere INFO o NONE,
// o configurato tramite variabili d'ambiente / config.
setLogLevel(levels.DEBUG);

export default logger;
