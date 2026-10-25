/**
 * @jest-environment jsdom
 *
 * The setup guide is one document in two languages. Both versions must carry the
 * same structure, and the commands must stay byte-identical: a translated
 * command is a broken install instruction.
 */
import fs from 'fs';
import path from 'path';

const contentCode = fs.readFileSync(
    path.resolve(__dirname, '../setupGuideContent.js'),
    'utf-8'
);

const loadContent = () => {
    delete window.SetupGuideContent;
    eval(contentCode);
    return window.SetupGuideContent;
};

// Describes the shape of a value: object keys, array lengths, string leaves.
const shapeOf = (value) => {
    if (typeof value === 'string') return 'string';
    if (Array.isArray(value)) return value.map(shapeOf);
    if (value && typeof value === 'object') {
        return Object.keys(value).sort().reduce((shape, key) => {
            shape[key] = shapeOf(value[key]);
            return shape;
        }, {});
    }
    return typeof value;
};

const collectStrings = (value, found = []) => {
    if (typeof value === 'string') {
        found.push(value);
    } else if (Array.isArray(value)) {
        value.forEach((item) => collectStrings(item, found));
    } else if (value && typeof value === 'object') {
        Object.values(value).forEach((item) => collectStrings(item, found));
    }
    return found;
};

const codeBlocksOf = (steps) => {
    const blocks = [];
    steps.forEach((step) => {
        step.blocks.forEach((block) => {
            if (block.code) blocks.push(block.code);
        });
    });
    return blocks;
};

describe('setupGuideContent', () => {
    it('ships both languages', () => {
        const content = loadContent();

        expect(Object.keys(content).sort()).toEqual(['en', 'es']);
    });

    it('keeps both languages structurally identical', () => {
        const { es, en } = loadContent();

        expect(shapeOf(es)).toEqual(shapeOf(en));
    });

    it('has no empty copy', () => {
        const content = loadContent();

        Object.entries(content).forEach(([language, document]) => {
            const empty = collectStrings(document).filter((text) => text.trim() === '');
            expect({ language, empty }).toEqual({ language, empty: [] });
        });
    });

    it('never translates a command or a variable name', () => {
        const { es, en } = loadContent();

        expect(codeBlocksOf(es.steps)).toEqual(codeBlocksOf(en.steps));
        expect(es.env.map((row) => row[0])).toEqual(en.env.map((row) => row[0]));
    });

    it('covers the seven setup steps plus the reference sections', () => {
        const { es } = loadContent();

        expect(es.steps).toHaveLength(7);
        expect(es.steps.map((step) => step.n)).toEqual([1, 2, 3, 4, 5, 6, 7]);
        expect(es.env.length).toBeGreaterThanOrEqual(4);
        expect(es.troubleshooting.length).toBeGreaterThanOrEqual(5);
        expect(es.topology.nodes).toHaveLength(4);
    });

    it('names the same file in both languages, so support can follow either one', () => {
        const { es, en } = loadContent();

        expect(es.sources).toEqual(en.sources);
        expect(es.sources.join(' ')).toContain('deploy/MT5_BRIDGE.md');
        expect(es.sources.join(' ')).toContain('docs/CLOUD.md');
    });
});
