import numpy as np
from dl_model import dl_model
import utils
from copy import deepcopy
import pickle
import beam_search

# prevents underflow
func = np.log
inv_func = np.exp


def edit_distance(s1, s2, prob_ins, prob_del, prob_replacement):
    """
    Score for converting s1 into s2. Both s1 and s2 is a vector of phone IDs and not phones
    :param s1: string 1
    :param s2: string 2
    :param prob_ins: 38x1 array of insert probabilities for each phone
    :param prob_del: 38x1 array of delete probabilities for each phone
    :param prob_replacement: matrix of size 38x38
    :return:
    """
    m, n = len(s1), len(s2)
    prob_ins, prob_del, prob_replacement = np.array(func(prob_ins)), np.array(func(prob_del)), np.array(
        func(prob_replacement))

    dp = np.zeros((m + 1, n + 1))

    for i in range(m + 1):
        for j in range(n + 1):

            if i == 0:
                dp[i][j] = np.sum(prob_ins[s2[:j]])
            elif j == 0:
                dp[i][j] = np.sum(prob_del[s1[:i]])
            elif s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                remove, insert, replace = prob_del[s1[i - 1]], prob_ins[s2[j - 1]], prob_replacement[s1[i - 1]][
                    s2[j - 1]]
                dp[i][j] = max(dp[i - 1][j] + remove, dp[i][j - 1] + insert, dp[i - 1][j - 1] + replace)

    return dp


def generate_lattice(outputs, blank_token_id, decode_type, top_n, collapse_type='max', print_final_lattice=False):
    """
    Generates lattice from outputs so that graph traversal can be used
    :param outputs: tsteps x num_phones matrix generated by LSTM
    :param blank_token_id: id of blank token used for CTC
    :param decode_type: if CTC, use CTC decoder, else return best
    :param top_n: how many best sequences to return
    :param collapse_type: if simple argmax, whether to sum neighbouring probs or take max
    :param print_final_lattice: whether to print the final lattice
    :return: [[phones above threshold and probabilities] after collapsing]
    """

    if decode_type == 'CTC':
        lattices = beam_search.decode(outputs, top_n, blank_token_id)
        if print_final_lattice:
            print('Final lattices:', lattices)
        return lattices

    elif decode_type == 'max':

        if top_n > 5:
            print("Logic works only for top-5 lattices")
            exit(0)

        tsteps, num_phones = outputs.shape
        init_lattice = []
        second_best = []

        for i in range(tsteps):
            phone_id = np.argmax(outputs[i])
            prob = outputs[i][phone_id]
            init_lattice.append((phone_id, prob))
            # extract second best
            outputs[i][phone_id] = -1
            phone_id = np.argmax(outputs[i])
            prob = outputs[i][phone_id]
            second_best.append((phone_id, prob, i))

        second_best = sorted(second_best, key=lambda x: x[1], reverse=True)
        best_lattices = [init_lattice]
        # for i in range(top_n-1):
        #     cur_lat = init_lattice.copy()
        #     new_ph, new_prob, frame_no = second_best[i]
        #     cur_lat[frame_no] = (new_ph, new_prob)
        #     best_lattices.append(cur_lat)
        first_two_larger = None
        if top_n > 1:
            cur_lat = init_lattice.copy()
            new_ph, new_prob, frame_no = second_best[0]
            cur_lat[frame_no] = (new_ph, new_prob)
            best_lattices.append(cur_lat)
        if top_n > 2:
            cur_lat = init_lattice.copy()
            new_ph, new_prob, frame_no = second_best[1]
            cur_lat[frame_no] = (new_ph, new_prob)
            best_lattices.append(cur_lat)
        if top_n > 3:
            cur_lat = init_lattice.copy()
            new_ph1, new_prob1, frame_no1 = second_best[0]
            new_ph2, new_prob2, frame_no2 = second_best[1]
            new_ph3, new_prob3, frame_no3 = second_best[2]
            if new_prob1 * new_prob2 > new_prob3:
                print("First two larger than 3rd")
                first_two_larger = True
                cur_lat[frame_no1] = (new_ph1, new_prob1)
                cur_lat[frame_no2] = (new_ph2, new_prob2)
            else:
                first_two_larger = False
                cur_lat[frame_no3] = (new_ph3, new_prob3)
            best_lattices.append(cur_lat)
        if top_n > 4:
            cur_lat = init_lattice.copy()
            if first_two_larger:
                new_ph3, new_prob3, frame_no3 = second_best[2]
                cur_lat[frame_no3] = (new_ph3, new_prob3)
            else:
                new_ph1, new_prob1, frame_no1 = second_best[0]
                new_ph2, new_prob2, frame_no2 = second_best[1]
                new_ph4, new_prob4, frame_no4 = second_best[3]
                if new_prob1 * new_prob2 > new_prob4:
                    print("First two larger than 4th")
                    cur_lat[frame_no1] = (new_ph1, new_prob1)
                    cur_lat[frame_no2] = (new_ph2, new_prob2)
                else:
                    cur_lat[frame_no4] = (new_ph4, new_prob4)
            best_lattices.append(cur_lat)

        to_return = []

        for cur_lattice in best_lattices:

            # Collapse consecutive
            lattice = []

            previous_phone = cur_lattice[0][0]
            prev_prob = cur_lattice[0][1]
            num = 1

            for cur in cur_lattice[1:]:
                id, cur_prob = cur[0], cur[1]

                if id == previous_phone:
                    num += 1
                    if collapse_type == 'sum':
                        prev_prob += cur_prob
                    else:
                        prev_prob = max(prev_prob, cur_prob)

                else:
                    if collapse_type == 'sum':
                        lattice.append((previous_phone, prev_prob / num))
                    elif collapse_type == 'max':
                        lattice.append((previous_phone, prev_prob))

                    previous_phone = id
                    prev_prob = cur_prob
                    num = 1
            # for the last sequence
            if collapse_type == 'sum':
                lattice.append((previous_phone, prev_prob / num))
            elif collapse_type == 'max':
                lattice.append((previous_phone, prev_prob))

            # Remove blank tokens
            final_lattice = [x for x in lattice if x[0] != blank_token_id]

            to_return.append(final_lattice)

        if print_final_lattice:
            print('Final lattices')
            for l in to_return:
                print(l)

        return to_return

    else:
        print("Decode type should be either CTC or max")
        exit(0)


def traverse_best_lattice(lattices, decode_type, target_string, insert_prob, del_prob, replace_prob):
    """
    Takes top-1 lattice and finds the best subsequence according to edit distance
    :param lattices: [[[phones above threshold and probabilities] after collapsing] list of such possible lattices]
    :param decode_type: CTC or max
    :param target_string: reference string to manipulate
    :param insert_prob: insertion probabilities
    :param del_prob: deletion probabilities
    :param replace_prob: substitution probabilities
    :return: best subsequence as ids of phones
    """
    if decode_type == 'CTC':

        overall_best = -np.inf
        overall_sub = []

        for lattice, lattice_score in lattices:

            prev_best = -np.inf
            best_subsequence = []

            m = len(lattice)
            n = len(target_string)

            for i in range(m):
                cur_string = lattice[i:]
                edit_matrix = edit_distance(target_string, cur_string, insert_prob, del_prob, replace_prob)
                for j in range(i, m):
                    final_score = edit_matrix[n][j - i + 1]
                    if final_score > prev_best:
                        # print("FOUND BEST")
                        prev_best = final_score
                        best_subsequence = cur_string[:j - i + 1]

            if prev_best + lattice_score > overall_best:  # add weighting here
                overall_best = prev_best + lattice_score
                overall_sub = best_subsequence

        return overall_sub

    elif decode_type == 'max':

        prev_best = -np.inf
        best_subsequence = []
        best_lat = 0

        for which_lat, lattice in enumerate(lattices):

            m = len(lattice)
            n = len(target_string)

            for i in range(m):
                cur_string = [x[0] for x in lattice[i:]]
                edit_matrix = edit_distance(target_string, cur_string, insert_prob, del_prob, replace_prob)
                prob = 0
                for j in range(i, m):
                    # log converts multiplication to addition
                    prob += func(lattice[j][1])
                    # n since first string is target string and we compare each subsequence with complete target string
                    final_score = prob + edit_matrix[n][j - i + 1]
                    # print('Final score (for i,j) = ({},{}) is {} + {} = {}'.format(i, j, prob, edit_matrix[n][j - i + 1],
                    #                                                                final_score))
                    if final_score > prev_best:
                        if which_lat != 0:
                            print("Found best in", str(which_lat+1), "lattice")
                        best_lat = which_lat
                        prev_best = final_score
                        best_subsequence = cur_string[:j - i + 1]

        return best_subsequence, lattices[best_lat]

    else:
        print("Decode type should be either CTC or max")
        exit(0)


def find_q_values(s1, s2, s2_node_prob, prob_ins, prob_del, prob_replacement):
    """
    Given best hypothesis and reference string, outputs the required Q scores for each phone
    :param s1: reference string
    :param s2: best hypotheses
    :param s2_node_prob: node probabilities obtained from LSTM
    :param prob_ins: score for inserting a phone
    :param prob_del: score for deleting a phone
    :param prob_replacement: confusion matrix
    :return: {phone1: [list of q vals], phone2: [list of qvals], ...}
    """
    m, n = len(s1), len(s2)
    dp = np.zeros((m + 1, n + 1))
    prob_ins, prob_del, prob_replacement, s2_node_prob = np.array(func(prob_ins)), np.array(func(prob_del)), np.array(
        func(prob_replacement)), func(np.array(s2_node_prob))
    # print('\nGround Truth:', s1, '\nBest Hypotheses:', s2, '\n')
    """
    op_dict is a dictionary of matching, inserting, deleting and replacing phones with the following convention:
    matching tuples - (index in reference, phone_id, lstm probability)
    insertion tuples - (index in hypotheses, phone_id, insertion prob of phone)
    deletion tuples - (index in reference, phone_id, deletion prob of phone)
    substitution tuples - (index in reference, old phone_id, index in hypotheses, new phone_id, replacement prob, new node prob)
    """
    op_dict = {}

    for i in range(m + 1):
        op_dict[i] = {}
        for j in range(n + 1):
            op_dict[i][j] = {'matches': [], 'insertions': [], 'deletions': [], 'substitutions': []}

    for i in range(m + 1):
        for j in range(n + 1):
            if i == 0:
                dp[i][j] = np.sum(prob_ins[s2[:j]])
                op_dict[i][j]['insertions'] = [(idx, s2[idx], prob_ins[s2[idx]], s2_node_prob[idx]) for idx in range(j)]
            elif j == 0:
                dp[i][j] = np.sum(prob_del[s1[:i]])
                op_dict[i][j]['deletions'] = [(idx, s1[idx], prob_del[s1[idx]]) for idx in range(i)]
            elif s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
                op_dict[i][j] = deepcopy(op_dict[i - 1][j - 1])
                op_dict[i][j]['matches'].append((i - 1, s1[i - 1], s2_node_prob[j - 1]))
            else:
                remove, insert, replace = prob_del[s1[i - 1]], prob_ins[s2[j - 1]], prob_replacement[s1[i - 1]][
                    s2[j - 1]]
                dp[i][j] = max(dp[i - 1][j] + remove, dp[i][j - 1] + insert, dp[i - 1][j - 1] + replace)

                if dp[i][j] == dp[i - 1][j] + remove:
                    op_dict[i][j] = deepcopy(op_dict[i - 1][j])
                    op_dict[i][j]['deletions'].append((i - 1, s1[i - 1], prob_del[s1[i - 1]]))
                elif dp[i][j] == dp[i][j - 1] + insert:
                    op_dict[i][j] = deepcopy(op_dict[i][j - 1])
                    op_dict[i][j]['insertions'].append((j - 1, s2[j - 1], prob_ins[s2[j - 1]], s2_node_prob[j - 1]))
                else:
                    op_dict[i][j] = deepcopy(op_dict[i - 1][j - 1])
                    op_dict[i][j]['substitutions'].append((i - 1, s1[i - 1], j - 1, s2[j - 1],
                                                           prob_replacement[s1[i - 1]][s2[j - 1]], s2_node_prob[j - 1]))

    final_dict = {}
    op_dict = op_dict[m][n]
    # print(op_dict, '\n')

    for match in op_dict['matches']:
        ph_id, prob = match[1], match[2]
        if not ph_id in final_dict.keys():
            final_dict[ph_id] = []
        final_dict[ph_id].append(inv_func(prob))

    for deletion in op_dict['deletions']:
        ph_id, prob = deletion[1], deletion[2]
        if not ph_id in final_dict.keys():
            final_dict[ph_id] = []
        final_dict[ph_id].append(inv_func(prob))

    for substi in op_dict['substitutions']:
        ph_id, prob_substi, node_prob = substi[1], substi[4], substi[5]
        if not ph_id in final_dict.keys():
            final_dict[ph_id] = []
        final_dict[ph_id].append(inv_func(prob_substi + node_prob))

    # for insertion in op_dict['insertions']:
    #     ph_id, prob, node_prob = insertion[1], insertion[2], insertion[3]
    #     if not ph_id in final_dict.keys():
    #         final_dict[ph_id] = []
    #     final_dict[ph_id].append(inv_func(prob + node_prob))

    # print(final_dict)
    return final_dict


def read_grtruth(filepath):
    # phones to be collapsed
    replacement = utils.replacement_dict()

    gr_phones = []
    with open(filepath, 'r') as f:
        a = f.readlines()
    for phenome in a:
        s_e_i = phenome[:-1].split(' ')  # start, end, phenome_name e.g. 0 5432 'aa'
        start, end, ph = int(s_e_i[0]), int(s_e_i[1]), s_e_i[2]

        # collapse into father phone
        for father, list_of_sons in replacement.items():
            if ph in list_of_sons:
                ph = father
                break
        gr_phones.append(ph)

    return gr_phones


if __name__ == '__main__':
    insert_prob, delete_prob, replace_prob = pickle.load(open('pickle/probs.pkl', 'rb'))
    a = dl_model('test_one')
    outputs, phone_to_id, id_to_phone = a.test_one(['trial/SI912.wav'])
    outputs = outputs[0]

    final_lattice = generate_lattice(outputs, a.model.blank_token_id, 'max', 3, print_final_lattice=True)

    gr_phones = read_grtruth('trial/SI912.PHN')
    gr_phone_ids = np.array([phone_to_id[x][0] for x in gr_phones])

    res = traverse_best_lattice(final_lattice, 'max', gr_phone_ids, insert_prob, delete_prob, replace_prob)
    res_phones = [id_to_phone[x] for x in res]
    print('Ground truth:', gr_phones, '\n', 'Predicted:', res_phones)
    exit(0)
    print(find_q_values(gr_phone_ids, res, [x[0][1] for x in final_lattice], insert_prob, delete_prob, replace_prob))
    # print(final_lattice, ([len(x) for x in final_lattice if len(x) != 1]))

    # phones = [[mapping[x[0]] for x in l] for l in final_lattice]
    # print(phones)
