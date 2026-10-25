/**
 * @jest-environment jsdom
 *
 * The login dictionary must give the ES/EN switch a predictable contract:
 * the browser decides the first language, the user's choice survives a reload,
 * and no translation can silently disappear.
 */
import fs from 'fs';
import path from 'path';

const moduleCode = fs.readFileSync(
    path.resolve(__dirname, '../loginI18n.js'),
    'utf-8'
);

const loadModule = () => {
    delete window.LoginI18n;
    eval(moduleCode);
    return window.LoginI18n;
};

const setBrowserLanguage = (language) => {
    Object.defineProperty(window.navigator, 'language', {
        value: language,
        configurable: true
    });
};

describe('loginI18n', () => {
    beforeEach(() => {
        window.localStorage.clear();
        setBrowserLanguage('es-AR');
    });

    describe('detectLanguage', () => {
        it('maps every Spanish locale to es and everything else to en', () => {
            const { detectLanguage } = loadModule();

            expect(detectLanguage('es')).toBe('es');
            expect(detectLanguage('es-AR')).toBe('es');
            expect(detectLanguage('es-419')).toBe('es');
            expect(detectLanguage('ES-ar')).toBe('es');
            expect(detectLanguage('en-US')).toBe('en');
            expect(detectLanguage('pt-BR')).toBe('en');
            expect(detectLanguage('')).toBe('en');
            expect(detectLanguage(undefined)).toBe('en');
            expect(detectLanguage(null)).toBe('en');
        });
    });

    describe('getLanguage', () => {
        it('uses the browser language on a first visit', () => {
            const { getLanguage } = loadModule();

            expect(getLanguage()).toBe('es');

            setBrowserLanguage('en-GB');
            expect(getLanguage()).toBe('en');
        });

        it('prefers the remembered choice over the browser language', () => {
            const { getLanguage, setLanguage } = loadModule();
            setLanguage('en');

            setBrowserLanguage('es-AR');

            expect(window.localStorage.getItem('ql_lang')).toBe('en');
            expect(getLanguage()).toBe('en');
        });

        it('ignores a remembered value that is not a supported language', () => {
            const { getLanguage } = loadModule();
            window.localStorage.setItem('ql_lang', 'fr');

            expect(getLanguage()).toBe('es');
        });
    });

    describe('t', () => {
        it('translates a given language without depending on the stored one', () => {
            const { tIn } = loadModule();
            window.localStorage.setItem('ql_lang', 'es');

            expect(tIn('es', 'form.title')).toBe('Iniciar sesión');
            expect(tIn('en', 'form.title')).toBe('Sign in');
            expect(tIn('en', 'label.password')).toBe('Password');
        });

        it('returns the copy of the active language', () => {
            const { getLanguage, setLanguage, t } = loadModule();

            expect(getLanguage()).toBe('es');
            expect(t('form.title')).toBe('Iniciar sesión');
            expect(t('action.signIn')).toBe('Iniciar sesión');
            expect(t('label.password')).toBe('Contraseña');

            setLanguage('en');

            expect(t('form.title')).toBe('Sign in');
            expect(t('action.signIn')).toBe('Sign in');
            expect(t('label.password')).toBe('Password');
        });

        it('falls back to English and then to the key itself, so a missing translation never renders empty', () => {
            const { dictionaries, setLanguage, t } = loadModule();
            setLanguage('es');

            const savedTitle = dictionaries.es['form.title'];
            delete dictionaries.es['form.title'];
            const savedSignInEs = dictionaries.es['action.signIn'];
            const savedSignInEn = dictionaries.en['action.signIn'];
            delete dictionaries.es['action.signIn'];
            delete dictionaries.en['action.signIn'];

            try {
                expect(t('form.title')).toBe('Sign in');
                expect(t('action.signIn')).toBe('action.signIn');
            } finally {
                dictionaries.es['form.title'] = savedTitle;
                dictionaries.es['action.signIn'] = savedSignInEs;
                dictionaries.en['action.signIn'] = savedSignInEn;
            }
        });
    });

    describe('setLanguage', () => {
        it('remembers the choice so the next load keeps it', () => {
            const { setLanguage } = loadModule();

            expect(setLanguage('en')).toBe('en');
            expect(window.localStorage.getItem('ql_lang')).toBe('en');

            const reloaded = loadModule();
            expect(reloaded.getLanguage()).toBe('en');
        });

        it('rejects an unsupported language without touching the stored one', () => {
            const { setLanguage } = loadModule();
            setLanguage('es');

            expect(() => setLanguage('fr')).toThrow(TypeError);
            expect(window.localStorage.getItem('ql_lang')).toBe('es');
        });
    });

    describe('applyStatic', () => {
        it('translates the labelled nodes of the pre-render surface', () => {
            const { applyStatic } = loadModule();
            document.body.innerHTML =
                '<p data-login-i18n="boot.loading">Loading</p>';

            applyStatic();
            expect(document.querySelector('p').textContent).toBe(
                'Cargando Quantum Llama...'
            );
        });

        it('re-applies the labels when the language changes', () => {
            const { applyStatic, setLanguage } = loadModule();
            document.body.innerHTML =
                '<p data-login-i18n="boot.loading">Loading</p>';
            applyStatic();

            setLanguage('en');

            expect(document.querySelector('p').textContent).toBe(
                'Loading Quantum Llama...'
            );
        });

        it('leaves an unknown label alone', () => {
            const { applyStatic } = loadModule();
            document.body.innerHTML =
                '<p data-login-i18n="nope.missing">Keep me</p>';

            applyStatic();

            expect(document.querySelector('p').textContent).toBe('Keep me');
        });
    });

    describe('dictionaries', () => {
        it('keeps both languages in sync and non-empty', () => {
            const { LANGUAGES, dictionaries } = loadModule();

            expect(LANGUAGES).toEqual(['es', 'en']);
            expect(Object.keys(dictionaries.es).sort()).toEqual(
                Object.keys(dictionaries.en).sort()
            );
            Object.entries(dictionaries).forEach(([language, copy]) => {
                const empty = Object.entries(copy)
                    .filter(([, value]) => typeof value !== 'string' || value.trim() === '')
                    .map(([key]) => `${language}:${key}`);
                expect(empty).toEqual([]);
            });
        });

        it('translates the login help and the session copy, not just the form', () => {
            const { dictionaries } = loadModule();
            const helpKeys = Object.keys(dictionaries.es).filter((key) =>
                key.startsWith('help.')
            );

            expect(helpKeys.length).toBeGreaterThanOrEqual(8);
            expect(dictionaries.es['help.bridge']).not.toBe(
                dictionaries.en['help.bridge']
            );
        });
    });
});
