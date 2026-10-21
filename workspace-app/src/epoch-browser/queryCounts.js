// Multi-field query runs and pages answer before their exact counts exist:
// totals are null and `counts` names one pending server job. Single-field runs
// carry exact totals and no pending job. Nothing here invents a count.
const count=value=>Number.isSafeInteger(value)&&value>=0;

/** The pending counts job named by a run/preview/page response, or null. */
export function pendingCountsRequest(data){
  const counts=data?.counts;
  return counts?.status==='pending'&&typeof counts.request_id==='string'&&counts.request_id?counts.request_id:null;
}

/** Validate a ready counts job result: exact non-negative epoch and cell counts. */
export function queryCountsResult(receipt,requestId){
  if(receipt?.request_id!==requestId)throw Error('Counts job identity changed. Run the query again.');
  const result=receipt.result;
  if(!count(result?.matched_count)||!count(result?.cell_count))throw Error('Counts job returned incomplete counts.');
  return {matched_count:result.matched_count,cell_count:result.cell_count};
}

/** Fill only the totals a pending response left null with the job's exact counts. */
export function withQueryCounts(data,job){
  if(!data||job?.status!=='ready'||!job.result||!pendingCountsRequest(data))return data;
  const {matched_count,cell_count}=job.result;
  return {...data,matched_count:data.matched_count??matched_count,
    ...(data.tree?{tree:{...data.tree,count:data.tree.count??matched_count}}:{}),
    ...(data.catalog?{catalog:{...data.catalog,total:data.catalog.total??matched_count}}:{}),
    ...(data.last_run?{last_run:{...data.last_run,epoch_count:data.last_run.epoch_count??matched_count,cell_count:data.last_run.cell_count??cell_count}}:{}),
    counts:{...data.counts,status:'ready'}};
}
