export type Motion = 'net_new' | 'expansion' | 'customer_hold';
export type Basis = 'fact' | 'hypothesis' | 'unknown' | 'scenario';
export type Review = 'unreviewed' | 'accepted' | 'edited' | 'rejected';
export interface Source { id:string; accountId:string; title:string; text:string; url:string|null; date:string|null; kind:'public'|'scenario'; }
export interface Contact { id:string; accountId:string; name:string; title:string; function:string; url:string|null; linkedin:string|null; email:string; emailVerified:false; titleStatus:string; researchedAt:string; uncertainty:string; }
export interface Account { id:string; name:string; domain:string; strategy:string; fundContext:string; fitBasis:string; motion:Motion; motionSynthetic:true; holdReason:string|null; sourceIds:string[]; eventIds:string[]; discoveryQuestions:string[]; }
export interface Dataset { version:string; asOf:string; accounts:Account[]; contacts:Contact[]; sources:Source[]; }
export interface Policy { version:string; warmDays:number; hotDays:number; }
export type DriverId = 'timing'|'fit'|'reach'|'evidence';
export interface ScoreDriver { id:DriverId; label:string; points:number; max:number; detail:string; }
// Rules-based propensity to engage, 0–10. A starting point for research, not a purchase prediction.
export interface AccountScore { total:number; max:10; drivers:ScoreDriver[]; }
export interface RankedAccount extends Account { fit:'Plausible'|'High'|'Low'|'Unresolved'; temperature:'Warm'|'Hot'|'Cold'|'Unknown'; priority:'P1'|'P2'|'Review'|'Hold'|'Expansion'; reason:string; nextAction:string; health:string; activeSourceIds:string[]; missing:string[]; score:AccountScore|null; }
export interface PlanField { id:string; label:string; value:string; basis:Basis; sourceIds:string[]; review:Review; reviewedAt?:string; buyerConfirmed:false; }
export interface Plan { accountId:string; fields:PlanField[]; questions:string[]; actions:string[]; signature:string; approvedSignature:string|null; generatedBy:'template'|'deepseek'; generatedAt:string; email?:PlanEmail; }
export interface PlanEmail { contactId:string; subject:string; body:string; }
export interface RunRecord { id:string; accountId:string; startedAt:string; elapsedMs:number; status:'success'|'failed'; provider:string; inputTokens?:number; outputTokens?:number; error?:string; }
export interface WorkspaceState { version:1; sourceOverrides:Record<string,boolean>; plans:Record<string,Plan>; runs:RunRecord[]; previousBrief?:Brief; }
export interface BriefItem { accountId:string; name:string; priority:string; reason:string; nextAction:string; contact:string; review:string; }
export interface Brief { cadence:'daily'|'weekly'; asOf:string; items:BriefItem[]; exceptions:BriefItem[]; changeNote:string; }
export interface ModelResponse { account_id:string; fields:{id:string;label:string;value:string;basis:'hypothesis'|'unknown';source_ids:string[]}[]; questions:string[]; actions:string[]; provider?:string; elapsed_ms?:number; usage?:{prompt_tokens?:number;completion_tokens?:number}; }
export const DEFAULT_POLICY:Policy={version:'demo-policy-0.2',warmDays:90,hotDays:30};
