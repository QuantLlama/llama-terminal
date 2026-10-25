/**
 * @jest-environment jsdom
 *
 * The setup guide is a full screen, not a dialog floating over the login: it
 * must carry every step in both languages and keep the login's flat language.
 */
import React from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { transformSync } from '@babel/core';
import fs from 'fs';
import path from 'path';

const read = (relative) => fs.readFileSync(path.resolve(__dirname, relative), 'utf-8');

const compile = (source, filename) => transformSync(source, {
    filename,
    presets: [
        ['@babel/preset-env', { targets: { node: 'current' } }],
        '@babel/preset-react'
    ]
}).code;

const bootstrap = () => {
    delete window.LoginI18n;
    eval(read('../../lib/loginI18n.js'));
    delete window.SetupGuideContent;
    eval(read('../../lib/setupGuideContent.js'));
    delete window.SetupGuide;
    eval(compile(read('../SetupGuide.js'), 'SetupGuide.js'));
};

const setBrowserLanguage = (language) => {
    Object.defineProperty(window.navigator, 'language', {
        value: language,
        configurable: true
    });
};

describe('SetupGuide', () => {
    beforeEach(() => {
        global.React = React;
        window.localStorage.clear();
        setBrowserLanguage('es-AR');
        bootstrap();
    });

    afterEach(() => {
        cleanup();
        jest.restoreAllMocks();
    });

    const renderGuide = (props = {}) => {
        const onClose = props.onClose || jest.fn();
        const onLanguageChange = props.onLanguageChange || jest.fn();
        const utils = render(React.createElement(window.SetupGuide, {
            onClose,
            language: props.language,
            onLanguageChange
        }));
        return { ...utils, onClose, onLanguageChange };
    };

    describe('content', () => {
        it('walks the seven steps in Spanish', () => {
            renderGuide();

            expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Conecta la plataforma con tu máquina');
            expect(screen.getByRole('heading', { name: 'Instala MetaTrader 5 e inicia sesión en tu bróker' })).toBeTruthy();
            expect(screen.getByRole('heading', { name: 'Agrega cuentas de cripto (opcional)' })).toBeTruthy();
            expect(screen.getByText('Variables de entorno')).toBeTruthy();
            expect(screen.getByText('Problemas frecuentes')).toBeTruthy();
            expect(screen.queryByText('What it does')).toBeNull();
        });

        it('walks the seven steps in English', () => {
            renderGuide({ language: 'en' });

            expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Connect this platform to your machine');
            expect(screen.getByRole('heading', { name: 'Install MetaTrader 5 and log in to your broker' })).toBeTruthy();
            expect(screen.getByRole('heading', { name: 'Add crypto accounts (optional)' })).toBeTruthy();
            expect(screen.getByRole('heading', { name: 'Troubleshooting' })).toBeTruthy();
            expect(screen.queryByText('Problemas frecuentes')).toBeNull();
        });

        it('keeps the commands copy-pasteable in both languages', () => {
            const { unmount } = renderGuide();
            const spanishCommands = Array.from(document.querySelectorAll('pre code')).map((node) => node.textContent);
            unmount();

            renderGuide({ language: 'en' });
            const englishCommands = Array.from(document.querySelectorAll('pre code')).map((node) => node.textContent);

            expect(spanishCommands.length).toBeGreaterThan(3);
            expect(spanishCommands).toEqual(englishCommands);
        });

        it('shows the data path and the environment table', () => {
            renderGuide();

            expect(screen.getByText('Bridge mt5_server.py')).toBeTruthy();
            expect(screen.getByText('MT5_BRIDGE_TOKEN')).toBeTruthy();
            expect(screen.getByText('8081')).toBeTruthy();
        });
    });

    describe('language switch', () => {
        it('asks the owner of the language to change it instead of holding its own state', () => {
            const { onLanguageChange } = renderGuide();

            fireEvent.click(screen.getByRole('button', { name: 'en' }));

            expect(onLanguageChange).toHaveBeenCalledWith('en');
        });

        it('marks the active language', () => {
            renderGuide({ language: 'en' });

            expect(screen.getByRole('button', { name: 'en' }).getAttribute('aria-pressed')).toBe('true');
            expect(screen.getByRole('button', { name: 'es' }).getAttribute('aria-pressed')).toBe('false');
        });
    });

    describe('behaviour', () => {
        it('closes with the close button and with Escape', () => {
            const { onClose } = renderGuide();

            fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
            expect(onClose).toHaveBeenCalledTimes(1);

            fireEvent.keyDown(document, { key: 'Escape' });
            expect(onClose).toHaveBeenCalledTimes(2);
        });

        it('offers an index that jumps to each section', () => {
            renderGuide();

            const nav = screen.getByRole('navigation', { name: 'Contenido' });
            const links = Array.from(nav.querySelectorAll('a'));
            expect(links).toHaveLength(4);
            links.forEach((link) => {
                expect(document.querySelector(link.getAttribute('href'))).not.toBeNull();
            });
        });

        it('keeps every control reachable by keyboard', () => {
            const { container } = renderGuide();

            const controls = container.querySelectorAll('button, a');
            expect(controls.length).toBeGreaterThan(0);
            Array.from(controls).forEach((control) => {
                expect(control.className).toMatch(/focus-visible:(outline-none|ring)/);
            });
        });
    });

    describe('terminal design direction', () => {
        it('is a flat screen, not a generated modal', () => {
            const { container } = renderGuide();
            const html = container.innerHTML;

            expect(html).not.toMatch(/gradient/i);
            expect(html).not.toMatch(/rounded-(xl|2xl|3xl|full)/);
            expect(html).not.toMatch(/backdrop-blur/);
            expect(html).not.toMatch(/drop-shadow|shadow-\[/);
            expect(html).not.toMatch(/<svg/i);
        });

        it('uses the same tokens and the same readable scale as the login', () => {
            const { container } = renderGuide();
            const sizeOf = (node) => {
                const match = (node.className || '').match(/text-\[(\d+(?:\.\d+)?)px\]/);
                return match ? parseFloat(match[1]) : null;
            };

            expect(container.querySelector('.bg-bg')).not.toBeNull();
            expect(container.querySelector('.border-border')).not.toBeNull();
            expect(sizeOf(screen.getByRole('heading', { level: 1 }))).toBeGreaterThanOrEqual(14);
            expect(sizeOf(container.querySelector('pre'))).toBeGreaterThanOrEqual(12);
        });

        it('collapses to one column on narrow screens', () => {
            const { container } = renderGuide();
            const grid = container.querySelector('main.grid');

            expect(grid.className).toContain('grid-cols-1');
            expect(grid.className).toContain('lg:grid-cols-');
        });
    });
});
