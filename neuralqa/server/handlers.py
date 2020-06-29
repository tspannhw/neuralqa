
from flask import jsonify, request, render_template
from neuralqa.model import BertModel
from neuralqa.searchindex import ElasticSearchIndex
import time


def init_model():
    model_name = "distilbert"
    model_path = "twmkn9/distilbert-base-uncased-squad2"
    model_type = "distilbert"
    model = BertModel(model_name, model_path)
    print(">> model loaded")
    return model


def init_index():
    index = ElasticSearchIndex()
    print(">> index connnection status", index.test_connection())
    return index


_model = init_model()
_index = init_index()


def _get_answer():
    """Generate an answer for the given search query.
    Performed as two stage process
    1.) Get sample passages from neighbourhood provided by matches by elastic search
    2.) Used BERT Model to identify exact answer spans

    Returns:
        [type] -- [description]
    """
    query_result = []
    result_size = 6
    question = "what is a fourth amendment right violation? "
    highlight_span = 450
    token_stride = 50
    context_dataset = "manual"
    context = "The fourth amendment kind of protects the rights of citizens .. such that they dont get searched"

    if request.method == "POST":
        data = request.get_json()
        result_size = data["size"]
        question = data["question"]
        context = data["context"]
        context_dataset = data["dataset"]
        token_stride = int(data["stride"])
        highlight_span = data["highlightspan"]
        model_name = data["modelname"]

    # load a different model if the selected model is different
    # if(_model.name != model_name):
    #     loaded_model_name, model, tokenizer = model_utils.load_model(
    #         model_name=model_name)

    included_fields = ["name"]
    search_query = {
        "_source": included_fields,
        "query": {
            "multi_match": {
                "query":    question,
                "fields": ["casebody.data.opinions.text", "name"]
            }
        },
        "highlight": {
            "fragment_size": highlight_span,
            "fields": {
                "casebody.data.opinions.text": {"pre_tags": [""], "post_tags": [""]},
                "name": {}
            }
        },
        "size": result_size
    }

    answer_holder = []
    response = {}
    start_time = time.time()

    # answer question based on provided context
    if (context_dataset == "manual"):
        answers = _model.answer_question(
            question, context, stride=token_stride)
        for answer in answers:
            answer["index"] = 0
            answer_holder.append(answer)
    # answer question based on retrieved passages from elastic search
    else:
        query_result = _index.run_query(search_query)
        for i, hit in enumerate(query_result["hits"]["hits"]):
            if ("casebody.data.opinions.text" in hit["highlight"]):
                # context passage is a concatenation of highlights
                context = " .. ".join(
                    hit["highlight"]["casebody.data.opinions.text"])
                answers = _model.answer_question(
                    question, context, stride=token_stride)
                for answer in answers:
                    answer["index"] = i
                    answer_holder.append(answer)

    # sort answers by probability
    answer_holder = sorted(
        answer_holder, key=lambda k: k['probability'], reverse=True)
    elapsed_time = time.time() - start_time
    response = {"answers": answer_holder, "took": elapsed_time}
    return jsonify(response)


def _get_passages():
    """Get a list of passages and highlights that match the given search query

    Returns:
        dictionary -- contains details on elastic search results.
    """
    query_result = []
    result_size, question, = 5, "motion in arrest judgment"
    opinion_excerpt_length = 500
    highlight_span = 350

    if request.method == "POST":
        data = request.get_json()
        result_size = data["size"]
        question = data["question"]
        highlight_span = data["highlightspan"]

    included_fields = ["name"]

    # return only included fields + script_field,
    # limit response to top result_size matches return highlights
    search_query = {
        "_source": included_fields,
        "query": {
            "multi_match": {
                "query":    question,
                "fields": ["casebody.data.opinions.text", "name"]
            }
        },
        "script_fields": {
            "opinion_excerpt": {
                "script": "(params['_source']['casebody']['data']['opinions'][0]['text']).substring(0," + str(opinion_excerpt_length) + ")"
            }
        },
        "highlight": {
            "fragment_size": highlight_span,
            "fields": {
                "casebody.data.opinions.text": {},
                "name": {}
            }
        },
        "size": result_size
    }

    query_result = _index.run_query(search_query)
    return jsonify(query_result)


def _get_explanation():
    """Return  an explanation for a given model

    Returns:
        [dictionary]: [explanation , query, question, ]
    """

    question = "what is the height of the eiffel tower"
    context = "the eiffel tower is 800m tall"

    if request.method == "POST":
        data = request.get_json()
        question = data["question"]
        context = data["context"].replace("<em>", "").replace("</em>", "")

    gradients, token_words, token_types, answer_text = _model.explain_model(
        question, context)

    explanation_result = {"gradients": gradients,
                          "token_words": token_words,
                          "token_types": token_types,
                          "answer": answer_text
                          }
    return jsonify(explanation_result)


def _test_handler():
    return jsonify("bingo")


def get_endpoints():
    return HANDLERS


HANDLERS = [
    ("/test", _test_handler, ['GET', 'POST']),
    ("/answer", _get_answer, ['GET', 'POST']),
    ("/explain", _get_explanation, ['GET', 'POST']),
    ("/passages", _get_passages, ['GET', 'POST']),
]