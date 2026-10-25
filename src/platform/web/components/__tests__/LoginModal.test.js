/**
 * @jest-environment jsdom
 *
 * The login redesign must keep two promises the request made explicit: the copy
 * exists in Spanish and English behind a switch, and the auth flow that was
 * already working keeps working.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { transformSync } from '@babel/core';
import fs from 'fs';
import path from 'path';

const i18nCode = fs.readFileSync(
    path.resolve(__dirname, '../../lib/loginI18n.js'),
    'utf-8'
);

const loadI18n = () => {
    delete window.LoginI18n;
    eval(i18nCode);
    return window.LoginI18n;
};

const loadLoginModal = () => {
    const source = fs.readFileSync(
        path.resolve(__dirname, '../LoginModal.js'),
        'utf-8'
    );
    // The page loads this file through in-browser Babel, so the test compiles it
    // the same way instead of depending on the file staying createElement-only.
    const compiled = transformSync(source, {
        filename: 'LoginModal.js',
        presets: [
            ['@babel/preset-env', { targets: { node: 'current' } }],
            '@babel/preset-react'
        ]
    }).code;
    delete window.LoginModal;
    eval(compiled);
    return window.LoginModal;
};

const setBrowserLanguage = (language) => {
    Object.defineProperty(window.navigator, 'language', {
        value: language,
        configurable: true
    });
};

// Compiling the component is the slow part; do it once and render it many times.
let LoginModal;
beforeAll(() => {
    global.React = React;
    LoginModal = loadLoginModal();
});

const renderLogin = ({ onLogin = jest.fn(), updateInfo } = {}) => {
    const utils = render(React.createElement(LoginModal, { onLogin, updateInfo }));
    return { ...utils, onLogin };
};

describe('LoginModal', () => {
    beforeEach(() => {
        window.localStorage.clear();
        global.React = React;
        loadI18n();
        setBrowserLanguage('es-AR');
        window.supabase = {
            auth: {
                signInWithPassword: jest.fn().mockResolvedValue({
                    data: { session: { access_token: 'token-123' } }
                }),
                signOut: jest.fn().mockResolvedValue({})
            }
        };
        window.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ is_subscribed: true })
        });
    });

    afterEach(() => {
        cleanup();
        jest.restoreAllMocks();
    });

    describe('language', () => {
        it('renders the whole surface in Spanish when the browser is Spanish', () => {
            renderLogin();

            expect(screen.getByRole('heading', { name: 'Iniciar sesión' })).toBeTruthy();
            expect(screen.getByLabelText('Email')).toBeTruthy();
            expect(screen.getByLabelText('Contraseña')).toBeTruthy();
            expect(screen.getByText('Recordar credenciales')).toBeTruthy();
            expect(screen.getByRole('button', { name: /Iniciar sesión/i })).toBeTruthy();
            expect(screen.getByText('Requisitos')).toBeTruthy();
            expect(screen.getByText('Primeros pasos')).toBeTruthy();
            expect(screen.queryByText('Requirements')).toBeNull();
        });

        it('renders the whole surface in English and remembers the choice', () => {
            renderLogin();

            fireEvent.click(screen.getByRole('button', { name: 'en' }));

            expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy();
            expect(screen.getByLabelText('Password')).toBeTruthy();
            expect(screen.getByText('Requirements')).toBeTruthy();
            expect(screen.getByText('First steps')).toBeTruthy();
            expect(screen.queryByText('Requisitos')).toBeNull();
            expect(window.localStorage.getItem('ql_lang')).toBe('en');
        });

        it('starts in English when the browser is English and nothing was chosen', () => {
            setBrowserLanguage('en-US');

            renderLogin();

            expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy();
        });

        it('keeps the switch on equal-width buttons so the header does not shift', () => {
            renderLogin();

            const spanish = screen.getByRole('button', { name: 'es' });
            const english = screen.getByRole('button', { name: 'en' });
            const widthOf = (node) => (node.className.match(/\bw-[\w[\]./-]+/) || [null])[0];

            expect(widthOf(spanish)).not.toBeNull();
            expect(widthOf(spanish)).toBe(widthOf(english));
            expect(screen.getByRole('group', { name: 'Idioma' })).toBeTruthy();
        });

        it('keeps what the user typed when the language changes', () => {
            renderLogin();
            const email = screen.getByLabelText('Email');
            fireEvent.change(email, { target: { value: 'trader@fund.com' } });

            fireEvent.click(screen.getByRole('button', { name: 'en' }));

            expect(screen.getByLabelText('Email').value).toBe('trader@fund.com');
        });

        it('translates the password visibility control', () => {
            renderLogin();

            const toggle = screen.getByRole('button', { name: 'Mostrar contraseña' });
            expect(toggle.getAttribute('aria-pressed')).toBe('false');

            fireEvent.click(toggle);

            expect(screen.getByRole('button', { name: 'Ocultar contraseña' }).getAttribute('aria-pressed')).toBe('true');
        });
    });

    describe('auth flow', () => {
        it('signs in with the typed credentials and hands the session to the app', async () => {
            const { onLogin } = renderLogin();

            fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'trader@fund.com' } });
            fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'secret' } });
            fireEvent.click(screen.getByRole('button', { name: /Iniciar sesión/i }));

            await waitFor(() => expect(onLogin).toHaveBeenCalledWith({ access_token: 'token-123' }));
            expect(window.supabase.auth.signInWithPassword).toHaveBeenCalledWith({
                email: 'trader@fund.com',
                password: 'secret'
            });
            expect(window.fetch).toHaveBeenCalledWith('/api/auth/session', {
                headers: { Authorization: 'Bearer token-123' }
            });
        });

        it('remembers the credentials only when the box is checked', async () => {
            renderLogin();

            fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'trader@fund.com' } });
            fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'secret' } });
            fireEvent.click(screen.getByLabelText('Recordar credenciales'));
            fireEvent.click(screen.getByRole('button', { name: /Iniciar sesión/i }));

            await waitFor(() => expect(window.localStorage.getItem('ql_email')).toBe('trader@fund.com'));
            expect(window.localStorage.getItem('ql_password')).toBe('secret');
            expect(window.localStorage.getItem('ql_remember')).toBe('true');
        });

        it('forgets the credentials when the box is unchecked', async () => {
            window.localStorage.setItem('ql_email', 'old@fund.com');
            window.localStorage.setItem('ql_password', 'old');
            window.localStorage.setItem('ql_remember', 'true');
            renderLogin();

            fireEvent.click(screen.getByLabelText('Recordar credenciales'));
            fireEvent.click(screen.getByRole('button', { name: /Iniciar sesión/i }));

            await waitFor(() => expect(window.localStorage.getItem('ql_remember')).toBe('false'));
            expect(window.localStorage.getItem('ql_email')).toBeNull();
            expect(window.localStorage.getItem('ql_password')).toBeNull();
        });

        it('shows a translated error and stays on the login when the credentials are wrong', async () => {
            window.supabase.auth.signInWithPassword = jest.fn().mockResolvedValue({
                error: { message: 'Invalid login credentials' }
            });
            const { onLogin } = renderLogin();

            fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'trader@fund.com' } });
            fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'wrong' } });
            fireEvent.click(screen.getByRole('button', { name: /Iniciar sesión/i }));

            await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
            expect(screen.getByRole('alert').textContent).toContain('Credenciales inválidas.');
            expect(onLogin).not.toHaveBeenCalled();

            fireEvent.click(screen.getByRole('button', { name: 'en' }));
            expect(screen.getByRole('alert').textContent).toContain('Invalid credentials.');
        });

        it('signs out and explains it when the account is not subscribed', async () => {
            window.fetch = jest.fn().mockResolvedValue({
                ok: true,
                json: async () => ({ is_subscribed: false, reason: 'expired' })
            });
            const { onLogin } = renderLogin();

            fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'trader@fund.com' } });
            fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'secret' } });
            fireEvent.click(screen.getByRole('button', { name: /Iniciar sesión/i }));

            await waitFor(() => expect(window.supabase.auth.signOut).toHaveBeenCalled());
            expect(screen.getByRole('alert').textContent).toContain('Acceso restringido');
            expect(screen.getByRole('alert').textContent).toContain('expired');
            expect(onLogin).not.toHaveBeenCalled();
        });
    });

    describe('terminal design direction', () => {
        it('uses flat surfaces instead of a floating rounded card', () => {
            const { container } = renderLogin();
            const html = container.innerHTML;

            expect(html).not.toMatch(/gradient/i);
            expect(html).not.toMatch(/rounded-(xl|2xl|3xl|full)/);
            expect(html).not.toMatch(/backdrop-blur/);
            expect(html).not.toMatch(/drop-shadow/);
        });

        it('builds the layout from the design tokens', () => {
            const { container } = renderLogin();

            expect(container.querySelector('.bg-bg')).not.toBeNull();
            expect(container.querySelector('.bg-accent')).not.toBeNull();
            expect(container.querySelector('.border-border')).not.toBeNull();
            expect(container.querySelector('.text-muted')).not.toBeNull();
        });

        it('shows brand, version and session state in the top rail', () => {
            renderLogin({ updateInfo: { stable_version: '1.9.0', update_required: false } });

            expect(screen.getByText('Quantum Llama')).toBeTruthy();
            expect(screen.getByText(/v1\.9\.0/)).toBeTruthy();
            expect(screen.getByText(/Sin sesión/)).toBeTruthy();
        });

        it('collapses to one column on narrow screens', () => {
            const { container } = renderLogin();
            const grid = container.querySelector('main.grid');

            expect(grid.className).toContain('grid-cols-1');
            expect(grid.className).toContain('lg:grid-cols-');
        });

        it('gives every control a visible keyboard focus ring', () => {
            const { container } = renderLogin();

            const controls = container.querySelectorAll('input, button, a');
            expect(controls.length).toBeGreaterThan(0);
            Array.from(controls).forEach((control) => {
                expect(control.className).toMatch(/focus-visible:(outline-none|ring)/);
            });
        });

        it('reads at arm length: headings, controls and labels sit above the small-print floor', () => {
            const { container } = renderLogin();
            const sizeOf = (node) => {
                const match = (node.className || '').match(/text-\[(\d+(?:\.\d+)?)px\]/);
                return match ? parseFloat(match[1]) : null;
            };

            expect(sizeOf(screen.getByRole('heading', { name: 'Iniciar sesión' }))).toBeGreaterThanOrEqual(18);
            expect(sizeOf(screen.getByLabelText('Email'))).toBeGreaterThanOrEqual(14);
            expect(sizeOf(screen.getByRole('button', { name: /Iniciar sesión/i }))).toBeGreaterThanOrEqual(12);
            expect(sizeOf(container.querySelector('label[for="login-email"]'))).toBeGreaterThanOrEqual(11);
        });

        it('marks the error and the password toggle for assistive technology', () => {
            const { container } = renderLogin();

            expect(container.querySelector('input#login-password').getAttribute('aria-invalid')).toBe('false');
            expect(
                container.querySelector('button[aria-label="Mostrar contraseña"]').getAttribute('aria-pressed')
            ).toBe('false');
        });
    });
});
