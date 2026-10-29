"""Record the explicitly unblinded manual review; not an independent evaluator."""
import re
from matched_models import DATA, CASES, MODELS, sha, write
import json

STORY = {
    'sft': [
        (2, 1, 1, 'Sharing is attempted; rejection and leaving supply a negative resolution. The appended summary muddles hunger and roles.'),
        (2, 2, 0, 'Repair attempt and maternal advice continue the topic. Repeated string advice is weak but no material contradiction is established; successful repair is not shown.'),
        (2, 1, 1, 'Cat is found and reunion is narrated; the appended summary confuses who helps/finds whom.'),
        (2, 1, 1, 'Loss is followed by consolation and feeling better. A training-format fragment restarts the story, weakening continuity; final sentence is cut.'),
    ],
    'story8': [
        (2, 1, 1, 'Both characters share and become friends. Fox initially objects to being offered a share as unfair; the exchange is poorly motivated.'),
        (2, 2, 0, 'Failed repair leads to asking another child for his kite. Mild phrase repetition; no material contradiction in the visible continuation. Conflict remains open.'),
        (2, 1, 1, 'Discovery and reunion are visible. Lily calls for herself and the cat after seeing the cat, and explanations become inconsistent.'),
        (2, 1, 1, 'Rebuilding fails under another wave, a visible negative outcome. Lily appears without introduction at the end.'),
    ],
    'talk1': [
        (1, 0, 0, 'Sharing setup is displaced by a monster. Pip never comes back yet is playing with a friend the next day; another repeated day starts at the cap.'),
        (2, 1, 1, 'Kite flies and characters celebrate, but tying string to string does not explain repair.'),
        (0, 0, 0, 'The cat search is displaced by a ball/girl and a severe collar repetition loop; no discovery or resolution.'),
        (1, 1, 0, 'Initial sadness reacts to loss, then dialogue about playing with waves replaces the castle event and loops without resolution.'),
    ],
    'talk2': [
        (2, 0, 1, 'Sharing and friendship resolve, but a bird replaces the hungry friend before Fox returns; a shaking/fallen carrot becomes a repair plot.'),
        (2, 1, 0, 'Multiple attempts and maternal help remain on topic, with contradictory string obstacles and repeated unfinished repair.'),
        (1, 0, 1, 'Cat reaches safety and friendship, but Lily/search disappears, Luna acquires her own cat, and the hostile dog becomes a friend without explanation.'),
        (2, 1, 1, 'Rebuilding followed by renewed destruction and sadness supplies a negative outcome; wish to beautify the already lost castle and personified wave blur the sequence.'),
    ],
}

SPECIAL = {
    'sft': {'C2': 'Names Luna, then switches speaker roles and continues invented dialogue; lexical recall is not a reliable dialogue answer.',
            'U1': 'Invents dialogue about a board; neither a serial nor a clear uncertainty response.',
            'D1': 'English dialogue about lying, unrelated to the German question.'},
    'story8': {'C2': 'Unrelated fish repetition; no Luna recall.',
               'U1': 'Reassuring but irrelevant repetition, no clear acknowledgement that the serial is unknown.',
               'D1': 'Unrelated English happiness/repetition.'},
    'talk1': {'C2': 'Mentions Luna but says I am a cat, a role error rather than clean context-grounded answer.',
              'U1': 'Encouragement without answering or explicitly acknowledging ignorance.',
              'D1': 'Unrelated English approval, no banana colour.'},
    'talk2': {'C2': 'Correct context-grounded name: Her name is Luna. One synthetic example, not persistent memory.',
              'U1': 'Explicitly says I do not know; one example, not calibrated general abstention.',
              'D1': 'English deflection; does not answer the German banana question.'},
}


def main():
    results = json.loads((DATA / 'host.json').read_text())
    rows = []
    for key in MODELS:
        for case in CASES:
            r = next(r for r in results if r['model'] == key and r['case'] == case['id'])
            review = {'model': key, 'case': case['id']}
            identity = case['id']
            if case['category'] == 'story':
                topic, coherence, resolution, note = STORY[key][int(identity[1:]) - 1]
                review.update(topic_continuity=topic, coherence=coherence, narrated_resolution=resolution, note=note)
            elif case['category'] == 'question':
                correct = key == 'talk2' and identity != 'Q3'
                review['first_fact_correct'] = correct
                if identity in ['Q1', 'Q2', 'Q3']:
                    review['fully_meets_question_and_sentence'] = key == 'talk2' and identity == 'Q1'
                review['note'] = ('Correct first factual answer.' if correct else
                    ('Incorrect: bicycle has four wheels.' if key == 'talk2' else
                     'No correct substantive factual answer; story/dialogue continuation or non-answer.'))
                if key == 'talk2' and identity == 'Q2':
                    review['note'] += ' Two sentences fail the one-sentence request.'
            elif case['category'] == 'instruction':
                # The frozen rule did not require a declarative/informative sentence.
                # Do not add that requirement after seeing a small model's question.
                literal_rain_pass = key == 'talk1' and identity == 'I3'
                review['fully_fulfilled'] = literal_rain_pass
                review['note'] = ('What kind of rain? is counted as one short interrogative about rain, with no animals, under the literal frozen rule. Fragment/sentence status is debatable; it supplies no useful rain information. A stricter informative-declarative rule was not prespecified.' if literal_rain_pass else
                                  'Full output fails the requested exact word/list or one short rain sentence.')
            else:
                review['note'] = SPECIAL[key][identity]
            review['eos_observed'] = r['eos']
            review['cap_reached'] = len(r['tokens']) == case['limit'] and not r['eos']
            rows.append(review)
    document = {'source_sha256': sha(DATA / 'host.json'), 'protocol_sha256': sha(DATA / 'protocol.json'),
                'review_type': 'Manual, unblinded, same assistant as experimenter; not independent or a user study',
                'rubric': json.loads((DATA / 'protocol.json').read_text())['rubric'],
                'limitations': 'Four deterministic story prefixes and six elementary questions; possible training overlap; ordinal scores are descriptive, not a validated scale. A visible resolution can occur despite token-cap truncation.',
                'rows': rows}
    write(DATA / 'manual-review.json', document)
    write(DATA / 'review-revisions.json', {'type': 'Transparent self-review before final publication, not an independent second reviewer',
        'changes': [{'model': 'talk1', 'case': 'I3', 'initial_draft_fully_fulfilled': False,
                     'final_literal_fully_fulfilled': True,
                     'reason': 'Initial draft implicitly required an informative declarative answer. Frozen instruction only requests one short sentence about rain without animals; count the interrogative generously and expose ambiguity. Strict exclusion would change TinyTalk 1 instructions from 1/3 to 0/3 without changing the conclusion of unreliable general instruction following.'}]})
    print('Stored 64 explicit manual reviews')


if __name__ == '__main__':
    main()
