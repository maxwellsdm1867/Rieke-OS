'use strict';

// The workspace renderer publishes this native title after selecting a project.
// A recovery/chooser window is evidence against a successful visible restore.
function projectWindowEvidence(titles, projectName, canReadTitles) {
  if (typeof projectName !== 'string' || !projectName.trim()) throw Error('Missing expected project name');
  const expected = projectName + ' · DISCO';
  if (titles.includes(expected)) return {state:'matched-project-title', title:expected};
  const visibleTitles = titles.filter(title => typeof title === 'string' && title.trim());
  if (visibleTitles.length) return {state:'unexpected-titles', titles:visibleTitles};
  if (!titles.length) return {state:'no-content-window'};
  return {state:canReadTitles ? 'awaiting-project-title' : 'visible-window-titles-unavailable'};
}

module.exports = {projectWindowEvidence};
