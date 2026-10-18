import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {PresentationFile,FileBlob} from '@oai/artifact-tool';
import {finalizePresentation} from '/Users/jueunyoo/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations/container_tools/artifact_tool_utils.mjs';
const root='/Users/jueunyoo/Documents/Curtin/RagChat/COMP6015-26S1-G13-RAGChatbot';
const skill='/Users/jueunyoo/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations';
const ref='/Users/jueunyoo/.codex/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/artifact-template-simple-light-mode/assets/reference.pptx';
const referenceSha256=createHash('sha256').update(await fs.readFile(ref)).digest('hex');
const p=await PresentationFile.importPptx(await FileBlob.load(ref));
const base=p.slides.items[3];
for(const s of [...p.slides.items]) if(s!==base)s.delete();
base.duplicate(); base.duplicate();
const data=[
 ['Our team’s direction','Local LLM\n\nFocus on finding the most relevant evidence','Conflict-aware RAG\n\nCompare rules within and across documents\n\nShow citations and request human review',
 'Our team decided to use a local LLM and focus on retrieval quality and conflict handling. We want the system to find the most relevant clauses, show supporting evidence, and highlight conflicting rules. When the evidence is unclear, it should ask for human review.'],
 ['My work with the new data','Two test documents\n\nDerived governance records\nSynthetic conflict scenarios\n\nNo OCR needed','Improvements\n\nBetter query matching\nUpdated hybrid scoring\nChecks for conflicting conditions',
 'I tested two new documents: a derived governance dataset and a synthetic conflict dataset. I kept reference answers out of the search index. I improved query matching and hybrid scoring, and added checks for eligibility requirements, approval conditions, and policy exceptions. This experiment used local LSA and rule-based responses, not LLM-generated answers.'],
 ['Results and next steps','Relevant evidence in top 5\n9/15 before, 13/15 after\n\nCorrect conflict pair reported\n14/20 before, 16/20 after\n\n75 regression tests passed','Next steps\n\nReview four missed cases\nTest with unseen questions\n\nDevelopment results on synthetic data',
 'For paraphrased questions, the system found the expected evidence in 13 out of 15 cases, compared with 9 before. It reported the correct conflict pair in 16 out of 20 cases, compared with 14 before. All 75 regression tests passed. These are development results on synthetic data. Next, I will investigate the missed cases and test with unseen questions. Source: experiment_outputs/text_only_20260909/REPORT_KO.md and before/after benchmark JSON files.']
];
for(let i=0;i<3;i++){
 const s=p.slides.items[i];const shapes=s.shapes.items;
 const title=shapes.find(x=>String(x.text).includes('Two column layout'));
 const bodies=shapes.filter(x=>String(x.text).includes('Lorem ipsum'));
 title.text=data[i][0];title.text.style={typeface:'Helvetica Neue',fontSize:46,bold:true,color:'#000000',autoFit:'none'};
 bodies.forEach((b,j)=>{b.text=data[i][j+1];b.text.style={typeface:'Helvetica Neue',fontSize:30,color:'#000000',autoFit:'none'};});
 for(const x of shapes){if(String(x.text)==='4')x.text=String(i+1);}
 s.speakerNotes.textFrame.setText(data[i][3]);
}
const candidatePath=root+'/report_build/progress_slides_sep16/candidate.pptx';
await (await PresentationFile.exportPptx(p)).save(candidatePath);
const finalPath=root+'/reports/progress_slides_sep16/RAG_Progress_Update.pptx';
await finalizePresentation({workspaceDir:root,candidatePath,finalPath,pythonExecutable:'/Users/jueunyoo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',integrityValidatorPath:skill+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:skill+'/container_tools/inspect_presentation_layout_geometry.py',layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],explicitTotalSlideCount:3,fontPolicy:{basis:'reference',families:['Helvetica Neue'],referencePath:ref,referenceSha256},verifyArtifactToolImport:true,receiptPath:root+'/report_build/progress_slides_sep16/validation.json'});
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(let i=0;i<3;i++)await fs.writeFile(root+`/report_build/progress_slides_sep16/slide-${i+1}.png`,new Uint8Array(await (await final.slides.items[i].export({format:'png',scale:1})).arrayBuffer()));
console.log(finalPath);
