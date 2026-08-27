---
name: context-bundler
description: Packages the current conversation into a structured handoff block so a fresh chat can resume the work with no loss of momentum. Use this whenever the user says "bundle this chat" or "prepare a continuation prompt", or a close variant of those phrases such as "bundle this conversation" or "bundle this for a new chat". When one of those phrases appears, stop the current task immediately and produce the handoff block, even mid-sentence and even if the current task feels unfinished.
---

# Context Bundler

The user is about to move this work into a fresh chat. That chat will see nothing except the block you produce. Everything it needs to keep working has to be inside the block.

## When to fire

Fire on "bundle this chat" or "prepare a continuation prompt", plus close variants of those two phrases. These are deliberately narrow triggers. Do not fire on general talk about context limits or starting over unless one of those phrases is used.

When it fires, drop the current topic at once. Do not finish the paragraph you were writing, do not ask whether the user wants the bundle now, do not offer to keep going first. Produce the block and nothing else.

## Output

Output plain markdown directly in the chat. No code fence, no greeting, no preamble, no closing offer, no commentary before or after. The block is the entire response.

Use this exact structure:

```
---
### 🚀 CONVERSATION CONTINUATION PROTOCOL

**Core Objective:** [The ultimate goal of the project in one clear sentence]

**Current Status & Key Milestones:**
* [Milestone achieved or decision made]
* [Data point or code structure finalized]
* [Constraint established by user]

**Critical Preferences & Constraints:**
* [Style, tone, tech stack, or rules to follow]

**Next Immediate Action:**
* [The exact task the user and AI need to execute right now]

**Prompt for the New AI Session:**
"You are continuing an advanced, ongoing collaboration. Use the context above to seamlessly resume the project. Do not introduce yourself or give a greeting. Acknowledge the context in one sentence by restating the Next Immediate Action, then begin working on it."
---
```

The final prompt paragraph is fixed text. Reproduce it verbatim every time rather than rewriting it to match the specific project.

## Filling it in

The single thing that makes a bundle work or fail is self-containment. The new session has no transcript, so any phrase that points backwards is dead weight. "The approach we discussed", "the file we were working on", "the bug from earlier" all arrive meaning nothing. Name the approach, name the file, describe the bug.

Concrete identifiers are what survive the handoff. Prefer exact versions, paths, model names, function names, error strings, and numbers over descriptions of them. "Qwen2-VL-7B served through vllm in a separate virtualenv at ~/vllm-env" is portable; "the vision model setup" is not.

**Core Objective** is the project, not the last thing discussed. If the conversation drifted, anchor on what the user is ultimately trying to produce.

**Current Status & Key Milestones** is a state snapshot, not a transcript. Three to seven bullets covering what is settled, what is built, and what numbers or structures are fixed. Include decisions that were considered and rejected, with the reason, because otherwise the new session will cheerfully propose them again. Leave out exploratory back-and-forth that led nowhere.

**Critical Preferences & Constraints** covers both stated rules and observed ones. If the user said to avoid em dashes, that goes in. If the user rejected two drafts for sounding too polished, that is a constraint even though it was never phrased as one. Include hard limits too: deadlines, hardware ceilings, budget, word counts, things that cannot change.

**Next Immediate Action** is exactly one task, specific enough that the new session can start on it without asking a clarifying question. If several threads are open, pick the one the user was actively working and mention the others under status.

## Code and long content

Short critical fragments go in verbatim: commands, config values, key parameters, file paths. These are usually what the new session needs first and they are cheap to include.

For anything long, describe it by path and purpose rather than pasting it, and say plainly that the user will need to re-share it. A bundle bloated with a full file is worse than one that tells the user which file to attach.

## Edge cases

If the conversation has barely started and there is genuinely nothing to bundle, say so in one sentence instead of producing a block padded with guesses. This is the only case where output other than the block is correct.

If the conversation covered several unrelated projects, bundle the one that was active most recently and note the others in a single status bullet, so the user can spot the omission and ask for a second bundle if they want one.

If the user adds an instruction alongside the trigger phrase, such as asking to focus on one thread or to include a specific detail, follow it and keep the rest of the format intact.
