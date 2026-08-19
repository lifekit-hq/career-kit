'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const h = require('../li-scrape.js');

const fixture = (name) => fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8');

test('parsePublicId', () => {
  assert.equal(
    h.parsePublicId('https://www.linkedin.com/in/yelyzaveta-morozova-496272408/'),
    'yelyzaveta-morozova-496272408',
  );
  assert.equal(
    h.parsePublicId('yelyzaveta-morozova-496272408'),
    'yelyzaveta-morozova-496272408',
  );
  assert.equal(
    h.parsePublicId('https://www.linkedin.com/in/foo-bar/details/skills/'),
    'foo-bar',
  );
  assert.equal(h.parsePublicId('https://www.linkedin.com/in/foo?utm=x#y'), 'foo');
  assert.equal(h.parsePublicId('https://www.linkedin.com/feed/'), null);
  assert.equal(h.parsePublicId(''), null);
  assert.equal(h.parsePublicId(null), null);
});

test('profileBase / sectionUrl / sectionName', () => {
  assert.equal(h.profileBase('id'), 'https://www.linkedin.com/in/id');
  assert.ok(h.sectionUrl('id', '').endsWith('/in/id/'));
  assert.equal(h.sectionUrl('id', ''), 'https://www.linkedin.com/in/id/');
  assert.equal(
    h.sectionUrl('id', 'details/skills'),
    'https://www.linkedin.com/in/id/details/skills/',
  );
  assert.equal(h.sectionName(''), 'profile');
  assert.equal(h.sectionName('details/skills'), 'skills');
});

test('isBlockedUrl', () => {
  assert.equal(h.isBlockedUrl('https://www.linkedin.com/authwall?x'), true);
  assert.equal(h.isBlockedUrl('https://www.linkedin.com/login'), true);
  assert.equal(h.isBlockedUrl('https://www.linkedin.com/checkpoint/xyz'), true);
  assert.equal(h.isBlockedUrl('https://www.linkedin.com/in/foo/'), false);
  assert.equal(h.isBlockedUrl(null), false);
  assert.equal(h.isBlockedUrl(undefined), false);
  assert.equal(h.isBlockedUrl(42), false);
});

test('outDirFor', () => {
  assert.equal(h.outDirFor('/tmp', 'foo'), '/tmp/out-foo');
  assert.equal(h.outDirFor('/tmp', 'foo', 'custom'), '/tmp/custom');
});

test('normalizeLines', () => {
  assert.deepEqual(h.normalizeLines('a\n\n  a \nb\nb\nc'), ['a', 'b', 'c']);
  assert.deepEqual(h.normalizeLines(''), []);
  assert.deepEqual(h.normalizeLines(null), []);
});

test('sliceSection', () => {
  const lines = h.sliceSection(fixture('experience.txt'), 'Experience');
  assert.equal(lines[0], 'Senior Widget Engineer');
  assert.ok(!lines.includes('More profiles for you'));
  assert.ok(!lines.includes('Jane Doe'));
});

test('splitCompanyType', () => {
  assert.deepEqual(h.splitCompanyType('Acme Corp · Full-time'), {
    company: 'Acme Corp',
    employmentType: 'Full-time',
  });
});

test('splitLocationArrangement', () => {
  assert.deepEqual(h.splitLocationArrangement('Berlin, Germany · Remote'), {
    location: 'Berlin, Germany',
    arrangement: 'Remote',
  });
  assert.deepEqual(h.splitLocationArrangement('Kyiv, Ukraine'), {
    location: 'Kyiv, Ukraine',
    arrangement: null,
  });
});

test('looksLikeDateLine', () => {
  assert.equal(h.looksLikeDateLine('Jan 2020 - Present · 4 yrs 6 mos'), true);
  assert.equal(h.looksLikeDateLine('Acme Corp · Full-time'), false);
});

test('stripDuration', () => {
  assert.equal(
    h.stripDuration('Jan 2020 - Present · 4 yrs 6 mos'),
    'Jan 2020 - Present',
  );
});

test('parseExperience', () => {
  const positions = h.parseExperience(fixture('experience.txt'));
  assert.equal(positions.length, 2);
  assert.deepEqual(positions[0], {
    title: 'Senior Widget Engineer',
    company: 'Acme Corp',
    employmentType: 'Full-time',
    dateRange: 'Jan 2020 - Present',
    location: 'Berlin, Germany',
    arrangement: 'Remote',
    description: ['Built widgets at scale.', 'Led the widget team.'],
  });
  assert.equal(positions[1].title, 'Junior Widget Maker');
  assert.equal(positions[1].arrangement, 'On-site');
  assert.deepEqual(positions[1].description, ['Made small widgets.']);
});

test('parseEducation', () => {
  const edu = h.parseEducation(fixture('education.txt'));
  assert.equal(edu.length, 2);
  assert.deepEqual(edu[0], {
    school: 'Fake State University',
    degree: "Master's Degree",
    field: 'Computer Science',
    dateRange: 'Sep 2016 - Jun 2018',
  });
  assert.equal(edu[1].school, 'Fake Community College');
});

test('parseSkills', () => {
  const skills = h.parseSkills(fixture('skills.txt'));
  assert.deepEqual(skills, [
    { name: 'Widget Design', endorsements: 5 },
    { name: 'Scaling Systems', endorsements: 3 },
    { name: 'Team Leadership', endorsements: 2 },
  ]);
});

test('extractEmail', () => {
  assert.equal(
    h.extractEmail('Email\nfoo.bar@example.com\nConnected'),
    'foo.bar@example.com',
  );
  assert.equal(h.extractEmail('no email here'), null);
});
