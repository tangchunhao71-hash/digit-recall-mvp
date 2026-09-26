"""Behavior checks for the self-contained Digit Recall page."""

from pathlib import Path
import json
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "index.html"


NODE_DRIVER = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');

function createGame(options = {}) {
  const ids = [
    'page-content', 'score', 'best', 'chances', 'phase', 'sequence', 'timer', 'timer-fill',
    'entry-form', 'answer', 'start-button', 'submit-button', 'share-button', 'hint',
    'tutorial-trigger', 'tutorial', 'tutorial-step', 'tutorial-title', 'tutorial-copy',
    'tutorial-sequence', 'tutorial-form', 'tutorial-answer', 'tutorial-feedback',
    'tutorial-next', 'tutorial-skip'
  ];
  const initiallyHidden = new Set(['timer', 'entry-form', 'share-button', 'tutorial', 'tutorial-form', 'tutorial-next']);
  const elements = Object.fromEntries(ids.map((id) => {
    const classes = new Set(initiallyHidden.has(id) ? ['hidden'] : []);
    return [id, {
      id,
      textContent: id === 'chances' ? '3 / 3' : '',
      value: '',
      maxLength: 30,
      disabled: false,
      inert: false,
      style: {},
      attributes: {},
      listeners: {},
      focused: false,
      classList: {
        add: (...names) => names.forEach((name) => classes.add(name)),
        remove: (...names) => names.forEach((name) => classes.delete(name)),
        contains: (name) => classes.has(name)
      },
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(name, handler) {
        (this.listeners[name] ||= []).push(handler);
      },
      focus() { this.focused = true; },
      dispatch(name, event = {}) {
        let result;
        for (const handler of this.listeners[name] || []) result = handler(event);
        return result;
      }
    }];
  }));

  const timers = new Map();
  let timerId = 0;
  const window = {
    location: { href: 'https://example.test/game/#top' },
    setTimeout(callback, delay) {
      const id = ++timerId;
      timers.set(id, { callback, delay });
      return id;
    },
    clearTimeout(id) { timers.delete(id); },
    prompt(message, value) { window.lastPrompt = { message, value }; },
    requestAnimationFrame(callback) { callback(); }
  };
  const storageData = new Map();
  if (options.savedBest !== undefined) storageData.set('digit-recall-best-v1', String(options.savedBest));
  if (options.tutorialSeen !== false) storageData.set('digit-recall-tutorial-seen-v1', 'yes');
  const storage = {
    data: storageData,
    writes: [],
    getItem(key) {
      if (options.storageThrows) throw new Error('storage blocked');
      return this.data.get(key) ?? null;
    },
    setItem(key, value) {
      if (options.storageThrows) throw new Error('storage blocked');
      this.data.set(key, value);
      this.writes.push([key, value]);
    }
  };
  const navigator = {};
  if (options.share) navigator.share = options.share;
  if (options.clipboard) navigator.clipboard = { writeText: options.clipboard };
  const mockMath = Object.create(Math);
  mockMath.random = () => 0.1;
  const context = {
    document: { getElementById: (id) => elements[id] },
    window,
    navigator,
    localStorage: storage,
    requestAnimationFrame: window.requestAnimationFrame,
    Math: mockMath
  };
  vm.runInNewContext(options.source, context);

  function advanceTimer() {
    const next = timers.entries().next().value;
    assert.ok(next, 'expected a scheduled game timer');
    const [id, timer] = next;
    timers.delete(id);
    timer.callback();
    return timer.delay;
  }
  function startToEntry() {
    elements['start-button'].dispatch('click');
    assert.equal(advanceTimer(), 450);
    assert.equal(elements.sequence.textContent, '111');
    assert.equal(advanceTimer(), 3000);
    assert.equal(elements['entry-form'].classList.contains('hidden'), false);
  }
  function submit(answer) {
    elements.answer.value = answer;
    elements['entry-form'].dispatch('submit', { preventDefault() {} });
  }
  return { elements, storage, window, timers, advanceTimer, startToEntry, submit };
}

async function main() {
  const source = require('node:fs').readFileSync(0, 'utf8');

  const firstVisit = createGame({ source, tutorialSeen: false });
  firstVisit.elements['start-button'].dispatch('click');
  assert.equal(firstVisit.elements.tutorial.classList.contains('hidden'), false);
  assert.equal(firstVisit.elements['page-content'].inert, true);
  assert.equal(firstVisit.elements['tutorial-step'].textContent, 'Step 1 of 3');
  assert.equal(firstVisit.advanceTimer(), 2200);
  assert.equal(firstVisit.elements['tutorial-step'].textContent, 'Step 2 of 3');
  assert.equal(firstVisit.elements['tutorial-form'].classList.contains('hidden'), false);
  firstVisit.elements['tutorial-answer'].value = '000';
  firstVisit.elements['tutorial-form'].dispatch('submit', { preventDefault() {} });
  assert.equal(firstVisit.elements.chances.textContent, '3 / 3', 'tutorial mistakes must not spend chances');
  assert.match(firstVisit.elements['tutorial-feedback'].textContent, /no chance is lost/);
  firstVisit.elements['tutorial-answer'].value = '427';
  firstVisit.elements['tutorial-form'].dispatch('submit', { preventDefault() {} });
  assert.equal(firstVisit.elements['tutorial-step'].textContent, 'Step 3 of 3');
  firstVisit.elements['tutorial-next'].dispatch('click');
  assert.equal(firstVisit.elements.tutorial.classList.contains('hidden'), true);
  assert.equal(firstVisit.elements['page-content'].inert, false);
  assert.equal(firstVisit.storage.data.get('digit-recall-tutorial-seen-v1'), 'yes');
  assert.equal(firstVisit.advanceTimer(), 450);
  assert.equal(firstVisit.elements.sequence.textContent, '111', 'tutorial should lead into the real game');

  const skippedTutorial = createGame({ source, tutorialSeen: false });
  skippedTutorial.elements['start-button'].dispatch('click');
  skippedTutorial.elements['tutorial-skip'].dispatch('click');
  assert.equal(skippedTutorial.storage.data.get('digit-recall-tutorial-seen-v1'), 'yes');
  assert.equal(skippedTutorial.advanceTimer(), 450, 'skip should start the real game immediately');

  const game = createGame({ source });
  game.startToEntry();
  game.submit('nope');
  assert.equal(game.elements.chances.textContent, '3 / 3', 'invalid input must not spend a chance');
  game.submit('111');
  assert.equal(game.elements.score.textContent, 1);
  assert.equal(game.elements.best.textContent, 1);
  assert.equal(game.storage.data.get('digit-recall-best-v1'), '1', 'new personal best should be saved');
  assert.equal(game.elements.chances.textContent, '3 / 3');
  assert.equal(game.advanceTimer(), 900);
  assert.equal(game.elements.sequence.textContent, '1111', 'each cleared level adds one digit');

  const retries = createGame({ source });
  retries.startToEntry();
  retries.submit('000');
  assert.equal(retries.elements.chances.textContent, '2 / 3');
  assert.equal(retries.elements.score.textContent, 0);
  assert.match(retries.elements.hint.textContent, /next try stays at 3 digits/);
  assert.equal(retries.advanceTimer(), 1100);
  assert.equal(retries.elements.sequence.textContent, '111', 'a missed level can be retried at the same length');
  retries.advanceTimer();
  retries.submit('000');
  assert.equal(retries.elements.chances.textContent, '1 / 3');
  retries.advanceTimer();
  retries.advanceTimer();
  retries.submit('000');
  assert.equal(retries.elements.phase.textContent, 'Game over');
  assert.equal(retries.elements['share-button'].classList.contains('hidden'), false);
  assert.equal(retries.elements['start-button'].textContent, 'Play again');
  assert.match(retries.elements.hint.textContent, /The sequence was 111/);

  retries.elements['share-button'].dispatch('click');
  assert.match(retries.window.lastPrompt.value, /I recalled 0 rounds in Digit Recall/);
  assert.match(retries.window.lastPrompt.value, /https:\/\/example\.test\/game\/$/);
  retries.elements['start-button'].dispatch('click');
  assert.equal(retries.elements.chances.textContent, '3 / 3', 'restarting restores all chances');
  assert.equal(retries.elements['share-button'].classList.contains('hidden'), true);
  assert.equal(retries.advanceTimer(), 450);
  assert.equal(retries.elements.sequence.textContent, '111');

  const nativeShare = createGame({
    source,
    share: async (data) => { nativeShare.data = data; }
  });
  nativeShare.startToEntry();
  nativeShare.submit('000');
  nativeShare.advanceTimer();
  nativeShare.advanceTimer();
  nativeShare.submit('000');
  nativeShare.advanceTimer();
  nativeShare.advanceTimer();
  nativeShare.submit('000');
  await nativeShare.elements['share-button'].dispatch('click');
  assert.equal(nativeShare.data.url, 'https://example.test/game/');
  assert.match(nativeShare.data.text, /Can you beat me/);

  const blockedStorage = createGame({ source, storageThrows: true });
  blockedStorage.startToEntry();
  blockedStorage.submit('111');
  assert.equal(blockedStorage.elements.best.textContent, 1, 'storage denial should not break play');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""


class DigitRecallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", cls.html, re.DOTALL)
        cls.game_script = scripts[-1]

    def test_seo_and_visible_rules_match_the_three_chance_game(self):
        self.assertIn("<title>Digit Recall — Free Number Memory Game</title>", self.html)
        self.assertIn("You get three chances", self.html)
        self.assertIn("three chances", self.html.lower())
        self.assertIn('id="share-button"', self.html)
        self.assertIn('role="dialog" aria-modal="true"', self.html)
        self.assertIn('id="tutorial-form"', self.html)
        self.assertIn("Try a guided practice", self.html)
        self.assertIn("@media (max-width: 520px)", self.html)
        self.assertIn('<meta name="theme-color" content="#fff8ec">', self.html)
        self.assertIn("color-scheme: light;", self.html)
        self.assertIn("--bg: #fff8ec;", self.html)
        self.assertIn(".stat:nth-child(1)", self.html)
        self.assertIn(".stats { gap: 7px; padding: 10px; }", self.html)
        self.assertIn(">Play now</button>", self.html)
        structured_data = re.search(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(structured_data)
        self.assertEqual(json.loads(structured_data.group(1))["name"], "Digit Recall")

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for game behavior checks")
    def test_gameplay_retry_scoring_storage_and_sharing(self):
        result = subprocess.run(
            [shutil.which("node"), "-e", NODE_DRIVER],
            input=self.game_script,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
