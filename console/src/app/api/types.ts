// Names for the generated API schema (npm run api:types regenerates schema.d.ts from ../api/openapi.json).
import type { components } from './schema';

type Schemas = components['schemas'];

export type User = Schemas['UserOut'];
export type Role = Schemas['Role'];
export type TokenOut = Schemas['TokenOut'];
export type Vacancy = Schemas['VacancyOut'];
export type VacancyIn = Schemas['VacancyIn'];
export type VacancyPatch = Schemas['VacancyPatch'];
export type VacancyStatus = Schemas['VacancyStatus'];
export type Requirement = Schemas['RequirementIO-Output'];
export type Ranking = Schemas['RankingOut'];
export type RankedCandidate = Schemas['RankedCandidate'];
export type Match = Schemas['MatchOut'];
export type RequirementResult = Schemas['RequirementResultOut'];
export type Evidence = Schemas['EvidenceOut'];
export type Candidate = Schemas['CandidateOut'];
export type SearchHit = Schemas['SearchHit'];
export type Application = Schemas['ApplicationOut'];
export type Stage = Schemas['Stage'];
export type Source = Schemas['Source'];
export type Note = Schemas['NoteOut'];
export type AuditEntry = Schemas['AuditOut'];
export type AuditVerify = Schemas['AuditVerifyOut'];
export type Overview = Schemas['OverviewOut'];
export type Skill = Schemas['SkillOut'];
export type Health = Schemas['HealthOut'];

export const STAGES: readonly Stage[] = [
  'new',
  'screening',
  'interview',
  'offer',
  'hired',
  'rejected',
];
