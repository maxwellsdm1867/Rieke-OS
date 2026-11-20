function validCoverage(coverage,sources){
  if(!coverage||!['complete','inventoried'].includes(coverage.status))return false;
  const counts=['checked_sources','inventories_recovered','recorded_attributes','inventoried_attributes','source_fields'];
  if(!counts.every(key=>Number.isSafeInteger(coverage[key])&&coverage[key]>=0))return false;
  return coverage.checked_sources===sources&&coverage.inventories_recovered<=sources
    &&coverage.inventoried_attributes===coverage.recorded_attributes
    &&(coverage.status==='inventoried'||coverage.searchable_source_fields===coverage.source_fields);
}

export function validMetadataRefresh(value){
  return !!value&&['sources','epochs','protocols','reused_sources','rebuilt_sources'].every(key=>Number.isInteger(value[key])&&value[key]>=0)&&
    (!('attribute_coverage' in value)||validCoverage(value.attribute_coverage,value.sources))&&
    typeof value.elapsed_seconds==='number'&&Number.isFinite(value.elapsed_seconds)&&value.elapsed_seconds>=0&&
    typeof value.completed_at==='string'&&Number.isFinite(Date.parse(value.completed_at));
}
export function availabilityLabel(status){
  return {available:'Available',missing:'File missing',unreadable:'Unreadable',changed:'File size changed'}[status] || 'Not checked';
}
export function availabilityExplanation(status){
  return status==='changed'?'The current file size differs from the registered source. This check does not validate file contents.':
    status==='available'?'The registered path is accessible. This is not a full checksum verification.':
    status==='missing'?'The registered source path was not found during this availability check.':
    status==='unreadable'?'The registered source path could not be read during this availability check.':'No availability result was reported.';
}
