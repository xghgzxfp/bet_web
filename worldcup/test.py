import datetime
import bson.json_util
import os
import pytest

from collections import OrderedDict
from freezegun import freeze_time

# setup a test tournament
from worldcup import config
config.TOURNAMENTS.append(config.Tournament(dbname='veryhard', league='欧联', display='硬糙', weight_schedule=[]))
config.DEFAULT_TOURNAMENT = config.TOURNAMENTS[-1]

from worldcup.app import app, logindb, tournamentdb as db
from worldcup import model


def drop_all():
    # login
    logindb.user.drop()
    # tournament
    db.gambler.drop()
    db.match.drop()
    db.auction.drop()


@pytest.fixture(autouse=True)
def setupforall():
    ctx = app.app_context()
    ctx.push()

    drop_all()
    yield
    # drop_all()


@pytest.fixture
def u0():
    return model.insert_user(name='u0', openid='openid-u0')


@pytest.fixture
def g1u():
    return model.insert_user(name='g1', openid='openid-g1')


@pytest.fixture
def g2u():
    return model.insert_user(name='g2', openid='openid-g2')


@pytest.fixture
def g3u():
    return model.insert_user(name='g3', openid='openid-g3')


@pytest.fixture
def g4u():
    return model.insert_user(name='g4', openid='openid-g4')


@pytest.fixture
def g1(g1u):
    return model.insert_gambler(g1u)


@pytest.fixture
def g2(g2u):
    return model.insert_gambler(g2u)


@pytest.fixture
def g3():
    return model.insert_gambler('g3')


@pytest.fixture
def g4(g4u):
    return model.insert_gambler('g4')


@pytest.fixture
def match1():
    # simple handicap
    return model.insert_match('硬糙', datetime.datetime(2018, 3, 31, 19, 30), '受一球', '水宫', '利浦', 2.08, 1.78, 2, 4)


@pytest.fixture
def match2():
    # complex handicap
    return model.insert_match('硬糙', datetime.datetime(2018, 3, 31, 22, 10), '半球/一球', '纽尔联', '哈尔德', 2.02, 1.84, 2, 1)


@pytest.fixture
def auction2():
    test_auctions = [
        dict(team='水宫', gambler='g4', price=12),
        dict(team='利浦', gambler='g3', price=21),
        dict(team='白顿', gambler='g2', price=32),
        dict(team='莱特城', gambler='g1', price=1),
        dict(team='曼特联', gambler='g2', price=3),
        dict(team='斯西', gambler='g3', price=4),
        dict(team='纽尔联', gambler='g4', price=6),
        dict(team='哈尔德', gambler='g1', price=123),
    ]
    for auc in test_auctions:
        model.insert_auction(**auc)


##########
# data retrieval tests
##########


def test_find_one_user(g1u):
    found = model.find_user_by_openid(g1u.openid)
    assert found is not None and found.name == g1u.name and found.openid == g1u.openid
    assert model.find_user_by_openid('non-existent') is None

    found = model.find_user_by_name(g1u.name)
    assert found is not None and found.name == g1u.name and found.openid == g1u.openid
    assert model.find_user_by_name('non-existent') is None


def test_model_find_gamblers(g1, g2, g3, g4):
    gamblers_found = model.find_gamblers()
    assert gamblers_found == [g1, g2, g3, g4]
    assert gamblers_found == [g1.name, g2.name, g3.name, g4.name]


def test_model_find_auction(auction2):
    auction_found = model.find_auction(team='纽尔联')
    assert auction_found is not None and auction_found.team == '纽尔联'


def test_model_find_team_owner(auction2, g4):
    team_owner = model.find_team_owner(team='纽尔联')
    assert team_owner == g4


def test_model_find_match_by_id(match1):
    found = model.find_match_by_id(match1.id)
    assert found == match1


def test_model_find_matches(match1, match2):
    matches_found = model.find_matches(reverse=False)
    assert matches_found == [match1, match2]

    matches_found = model.find_matches(reverse=True, limit=1)
    assert matches_found == [match2]


##########
# data manipulation tests
##########


def test_model_drop_user(auction2, match1, match2, g1):
    model.update_match_gamblers(match1.id, 'a', g1, cutoff_check=False)
    model.update_match_gamblers(match2.id, 'b', g1, cutoff_check=False)

    # drop user by name
    model.drop_user(g1.name)
    # user dropped successfully
    assert not model.find_user_by_name(g1.name)

    # match / auction remains untouched
    assert db.match.find({'a.gamblers': g1.name}).count() == 1
    assert db.match.find({'b.gamblers': g1.name}).count() == 1
    assert db.auction.find({'gambler': g1.name}).count() == 2


def test_model_update_user_name(auction2, match1, match2, g1, g2):
    G1_NEW = '巨型钻'

    model.update_match_gamblers(match1.id, 'a', g1, cutoff_check=False)
    model.update_match_gamblers(match2.id, 'b', g1, cutoff_check=False)

    model.update_user_name(current=g1.name, new=G1_NEW)
    # gambler
    assert model.find_user_by_name(G1_NEW)
    # match
    assert db.match.find({'a.gamblers': G1_NEW}).count() == 1
    assert db.match.find({'b.gamblers': G1_NEW}).count() == 1
    # auction
    assert db.auction.find({'gambler': G1_NEW}).count() == 2

    G2_NEW = '小型钻'

    model.update_match_gamblers(match1.id, 'b', g2, cutoff_check=False)
    model.update_match_gamblers(match2.id, 'b', g2, cutoff_check=False)

    model.update_user_name(current=g2.name, new=G2_NEW)
    # gambler
    assert model.find_user_by_name(G2_NEW)
    # match
    assert db.match.find({'a.gamblers': G2_NEW}).count() == 0
    assert db.match.find({'b.gamblers': G2_NEW}).count() == 2
    # auction
    assert db.auction.find({'gambler': G2_NEW}).count() == 2


def test_model_update_match_score(match1):
    model.update_match_score(match1.id, "1", "0")
    match_found = model.find_match_by_id(match1.id)
    assert match_found.a['score'] == 1 and match_found.b['score'] == 0

    model.update_match_score(match1.id, "2", "3")
    match_found = model.find_match_by_id(match1.id)
    assert match_found.a['score'] == 2 and match_found.b['score'] == 3


def test_model_update_match_handicap(match1):
    # freeze_time() 须为 utc 时间

    with freeze_time('2018-03-31 04:00:01'):
        model.update_match_handicap(match1.id, '半球/一球')
        match_found = model.find_match_by_id(match1.id)
        assert match_found.handicap_display == '受一球' and match_found.handicap == (-1, -1)

    with freeze_time('2018-03-31 03:59:59'):
        model.update_match_handicap(match1.id, '半球/一球', cutoff_check=False)
        match_found = model.find_match_by_id(match1.id)
        assert match_found.handicap_display == '半球/一球' and match_found.handicap == (0.5, 1)


def test_model_update_match_gamblers(match1, g1):
    # freeze_time() 须为 utc 时间

    # 盘口未定 不能投注
    with freeze_time('2018-03-31 03:59:59'):
        model.update_match_gamblers(match1.id, 'a', g1)
        match_found = model.find_match_by_id(match1.id)
        assert 'g1' not in match_found.a['gamblers'] and 'g1' not in match_found.b['gamblers']

    # 盘口已定 开赛前 第一次投注
    with freeze_time('2018-03-31 04:00:01'):
        model.update_match_gamblers(match1.id, 'a', g1)
        match_found = model.find_match_by_id(match1.id)
        assert 'g1' in match_found.a['gamblers'] and 'g1' not in match_found.b['gamblers']

    # 盘口已定 开赛前 改注
    with freeze_time('2018-03-31 04:00:03'):
        model.update_match_gamblers(match1.id, 'b', g1)
        match_found = model.find_match_by_id(match1.id)
        assert 'g1' not in match_found.a['gamblers'] and 'g1' in match_found.b['gamblers']

    # 开赛后 投注结果不再改变
    with freeze_time('2018-03-31 11:30:01'):
        model.update_match_gamblers(match1.id, 'a', g1)
        match_found = model.find_match_by_id(match1.id)
        assert 'g1' not in match_found.a['gamblers'] and 'g1' in match_found.b['gamblers']


def test_model_update_match_gamblers_signup(match1, u0):
    assert model.find_gamblers() == []
    model.update_match_gamblers(match1.id, 'a', u0, cutoff_check=False)
    assert model.find_gamblers() == [u0]


def test_model_update_match_weight(match1):
    model.update_match_weight(match1.id, 4)
    match_found = model.find_match_by_id(match1.id)
    assert match_found.weight == 4


def test_model_update_match_time(match1):
    orig_time = match1.match_time

    next_time = orig_time + datetime.timedelta(hours=1)
    next_id = model._generate_match_id(match_time=next_time, team_a=match1.a['team'], team_b=match1.b['team'])

    assert model.find_match_by_id(match_id=next_id) is None

    model.update_match_time(match_id=match1.id, match_time=next_time)

    assert model.find_match_by_id(match_id=next_id).match_time == next_time


##########
# calculation tests
##########


@pytest.mark.parametrize('choice_a,choice_b,no_choice,handicap,score_a,score_b,expected', [
    (['g1', 'g2'], ['g3', 'g4'],      [],       '球半', '3', '1', {'g1': 2, 'g2': 2, 'g3': -2, 'g4': -2}),  # 有胜负
    (['g1', 'g2'], ['g3', 'g4'],      [],       '平手', '0', '0', {'g1': 0,  'g2': 0,  'g3': 0, 'g4': 0}),  # 平局
    (['g1', 'g2'], ['g3', 'g4'],      [], '受半球/一球', '1', '2', {'g1': -1, 'g2': -1, 'g3': 1, 'g4': 1}),  # 赢一半
    (['g1', 'g2'],       ['g3'],  ['g4'],       '半球', '0', '0', {'g1': -2, 'g2': -2, 'g3': 6, 'g4': -2}),  # 未投注
    (['g1', 'g2', 'g3', 'g4'],  [],   [], '受一球/球半', '0', '0', {'g1': 0, 'g2': 0, 'g3': 0, 'g4': 0}),  # 全胜
    (['g1', 'g2', 'g3', 'g4'],  [],   [], '一球/球半', '0', '0',   {'g1': -2, 'g2': -2, 'g3': -2, 'g4': -2}),  # 全负
])
def test_Match_update_profit_and_loss_no_auction(choice_a, choice_b, no_choice, handicap, score_a, score_b, expected):
    # prepare gamblers
    choice_a = [model.insert_gambler(g) for g in choice_a]
    choice_b = [model.insert_gambler(g) for g in choice_b]
    no_choice = [model.insert_gambler(g) for g in no_choice]

    # prepare match
    match = model.insert_match('硬糙', datetime.datetime(2018, 3, 31, 19, 30), '受一球', '水宫', '利浦', 2.08, 1.78, 2, 4)

    # prepare bet choice
    for g in choice_a:
        model.update_match_gamblers(match.id, 'a', g, cutoff_check=False)

    for g in choice_b:
        model.update_match_gamblers(match.id, 'b', g, cutoff_check=False)

    # prepare match score
    model.update_match_score(match.id, score_a, score_b)

    # prepare match handicap
    model.update_match_handicap(match.id, handicap, cutoff_check=False)

    # calculate PNL
    match = model.find_match_by_id(match.id)
    result = match.update_profit_and_loss_result(required_gamblers=model.find_gamblers())

    for k, v in expected.items():
        assert result.get(k) == v


@pytest.mark.parametrize('choice_a,choice_b,no_choice,handicap,score_a,score_b,expected', [
    (['g1', 'g2'], ['g3', 'g4'],      [],       '球半', '3', '1', {'g1': 2, 'g2': 2, 'g3': -2, 'g4': -2}),  # 有胜负
    (['g1', 'g2'], ['g3', 'g4'],      [],       '平手', '0', '0', {'g1': 0,  'g2': 0,  'g3': 0, 'g4': 0}),  # 平局
    (['g1', 'g2'], ['g3', 'g4'],      [], '受半球/一球', '1', '2', {'g1': -1, 'g2': -1, 'g3': 2, 'g4': 2}),  # 赢一半
    (['g1', 'g2'],       ['g3'],  ['g4'],       '半球', '0', '0', {'g1': -2, 'g2': -2, 'g3': 12, 'g4': -2}),  # 未投注
    (['g1', 'g2', 'g3', 'g4'],  [],   [], '受一球/球半', '0', '0', {'g1': 0, 'g2': 0, 'g3': 0, 'g4': 0}),  # 全胜
    (['g1', 'g2', 'g3', 'g4'],  [],   [], '一球/球半', '0', '0',   {'g1': -2, 'g2': -2, 'g3': -2, 'g4': -2}),  # 全负
])
def test_Match_update_profit_and_loss_with_auction(choice_a, choice_b, no_choice, handicap, score_a, score_b, expected, auction2):
    # prepare gamblers
    choice_a = [model.insert_gambler(g) for g in choice_a]
    choice_b = [model.insert_gambler(g) for g in choice_b]
    no_choice = [model.insert_gambler(g) for g in no_choice]

    # prepare match
    match = model.insert_match('硬糙', datetime.datetime(2018, 3, 31, 19, 30), '受一球', '水宫', '利浦', 2.08, 1.78, 2, 4)

    # prepare bet choice
    for g in choice_a:
        model.update_match_gamblers(match.id, 'a', g, cutoff_check=False)

    for g in choice_b:
        model.update_match_gamblers(match.id, 'b', g, cutoff_check=False)

    # prepare match score
    model.update_match_score(match.id, score_a, score_b)

    # prepare match handicap
    model.update_match_handicap(match.id, handicap, cutoff_check=False)

    # calculate PNL
    match = model.find_match_by_id(match.id)
    result = match.update_profit_and_loss_result(required_gamblers=model.find_gamblers())

    for k, v in expected.items():
        assert result.get(k) == v


@pytest.mark.parametrize('choice_a,choice_b,no_choice,handicap,score_a,score_b,expected', [
    (['g1', 'g2'], ['g3', 'g4'],      [],       '球半', '3', '1', {'g1': 2, 'g2': 2, 'g3': -2, 'g4': -2}),  # 有胜负
    (['g1', 'g2'], ['g3', 'g4'],      [],       '平手', '0', '0', {'g1': 0,  'g2': 0,  'g3': 0, 'g4': 0}),  # 平局
    (['g1', 'g2'], ['g3', 'g4'],      [], '受半球/一球', '1', '2', {'g1': -1, 'g2': -1, 'g3': 1, 'g4': 2}),  # 赢一半
    (['g1', 'g2'],       ['g3'],  ['g4'],       '半球', '0', '0', {'g1': -2, 'g2': -2, 'g3': 6, 'g4': -2}),  # 未投注
    (['g1', 'g2', 'g3', 'g4'],  [],   [], '受一球/球半', '0', '0', {'g1': 0, 'g2': 0, 'g3': 0, 'g4': 0}),  # 全胜
    (['g1', 'g2', 'g3', 'g4'],  [],   [], '一球/球半', '0', '0',   {'g1': -2, 'g2': -2, 'g3': -2, 'g4': -2}),  # 全负
])
def test_Match_update_profit_and_loss_with_self_auction(choice_a, choice_b, no_choice, handicap, score_a, score_b, expected, auction2):
    # prepare gamblers
    choice_a = [model.insert_gambler(g) for g in choice_a]
    choice_b = [model.insert_gambler(g) for g in choice_b]
    no_choice = [model.insert_gambler(g) for g in no_choice]

    # prepare match
    match = model.insert_match('硬糙', datetime.datetime(2018, 4, 1, 20, 30), '平手', '水宫', '纽尔联', 1.01, 1.39, 0, 1)

    # prepare bet choice
    for g in choice_a:
        model.update_match_gamblers(match.id, 'a', g, cutoff_check=False)

    for g in choice_b:
        model.update_match_gamblers(match.id, 'b', g, cutoff_check=False)

    # prepare match score
    model.update_match_score(match.id, score_a, score_b)

    # prepare match handicap
    model.update_match_handicap(match.id, handicap, cutoff_check=False)

    # calculate PNL
    match = model.find_match_by_id(match.id)
    result = match.update_profit_and_loss_result(required_gamblers=model.find_gamblers())

    for k, v in expected.items():
        assert result.get(k) == v


def test_model_generate_series(g1, g2, g3, g4, match1, match2):
    results = [series.__dict__ for series in model.generate_series()]
    expected = [
        {'gambler': 'g1', 'points': OrderedDict([('201803311930-水宫-利浦', -2.0), ('201803312210-纽尔联-哈尔德', -4.0)])},
        {'gambler': 'g2', 'points': OrderedDict([('201803311930-水宫-利浦', -2.0), ('201803312210-纽尔联-哈尔德', -4.0)])},
        {'gambler': 'g3', 'points': OrderedDict([('201803311930-水宫-利浦', -2.0), ('201803312210-纽尔联-哈尔德', -4.0)])},
        {'gambler': 'g4', 'points': OrderedDict([('201803311930-水宫-利浦', -2.0), ('201803312210-纽尔联-哈尔德', -4.0)])}
    ]
    assert results == expected


##########
# integration tests
##########


def load_history(tournament):

    def _load_json(filename):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'history', tournament, filename)) as f:
            return [bson.json_util.loads(line) for line in f]

    db.gambler.insert_many(_load_json('gambler.json'))
    db.auction.insert_many(_load_json('auction.json'))
    db.match.insert_many(_load_json('match.json'))


def test_history_eurocup2016():
    load_history('eurocup2016')

    # sanity check
    assert db.gambler.find().count() == 8
    assert db.auction.find().count() == 24
    assert db.match.find().count() == 51

    # 用第一场和最后一场积分做校验
    # 积分保留两位小数转为字符串做比较
    results = []
    for s in [series.__dict__ for series in model.generate_series()]:
        points = [(k, '{:.2f}'.format(v)) for k, v in s['points'].items()]
        result = dict(gambler=s['gambler'], points=OrderedDict([points[0], points[-1]]))
        results.append(result)

    expected = [
        {'gambler': '大B', 'points': OrderedDict([('201606110300-法国-罗马尼亚', '-2.00'), ('201607110300-法国-葡萄牙', '-17.33')])},
        {'gambler': '李琛', 'points': OrderedDict([('201606110300-法国-罗马尼亚', '-2.00'), ('201607110300-法国-葡萄牙', '-17.40')])},
        {'gambler': '老大', 'points': OrderedDict([('201606110300-法国-罗马尼亚', '3.33'), ('201607110300-法国-葡萄牙', '39.53')])},
        {'gambler': '小白', 'points': OrderedDict([('201606110300-法国-罗马尼亚', '-2.00'), ('201607110300-法国-葡萄牙', '74.27')])},
        {'gambler': '老娘', 'points': OrderedDict([('201606110300-法国-罗马尼亚', '3.33'), ('201607110300-法国-葡萄牙', '-20.60')])},
        {'gambler': '老排', 'points': OrderedDict([('201606110300-法国-罗马尼亚', '6.67'), ('201607110300-法国-葡萄牙', '29.07')])},
        {'gambler': '大钻', 'points': OrderedDict([('201606110300-法国-罗马尼亚', '-2.00'), ('201607110300-法国-葡萄牙', '30.60')])},
        {'gambler': '老套', 'points': OrderedDict([('201606110300-法国-罗马尼亚', '-2.00'), ('201607110300-法国-葡萄牙', '14.67')])},
    ]

    assert results == expected


def test_history_worldcup2018():
    load_history('worldcup2018')

    # sanity check
    assert db.gambler.find().count() == 10
    assert db.auction.find().count() == 32
    assert db.match.find().count() == 64

    # 用第一场和最后一场积分做校验
    # 积分保留两位小数转为字符串做比较
    results = []
    for s in [series.__dict__ for series in model.generate_series()]:
        points = [(k, '{:.2f}'.format(v)) for k, v in s['points'].items()]
        result = dict(gambler=s['gambler'], points=OrderedDict([points[0], points[-1]]))
        results.append(result)

    expected = [
        {'gambler': '大B', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '-2.00'), ('201807152300-法国-克罗地亚', '42.67')])},
        {'gambler': '金帝', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '3.00'), ('201807152300-法国-克罗地亚', '-21.67')])},
        {'gambler': '老套', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '6.00'), ('201807152300-法国-克罗地亚', '-21.10')])},
        {'gambler': '小白', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '-2.00'), ('201807152300-法国-克罗地亚', '28.81')])},
        {'gambler': '老排', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '-2.00'), ('201807152300-法国-克罗地亚', '92.33')])},
        {'gambler': '大钻', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '-2.00'), ('201807152300-法国-克罗地亚', '71.24')])},
        {'gambler': '李琛', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '3.00'), ('201807152300-法国-克罗地亚', '-40.76')])},
        {'gambler': '老大', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '-2.00'), ('201807152300-法国-克罗地亚', '-57.81')])},
        {'gambler': '老娘', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '3.00'), ('201807152300-法国-克罗地亚', '57.24')])},
        {'gambler': '汉姆', 'points': OrderedDict([('201806142300-俄罗斯-沙地阿拉伯', '-2.00'), ('201807152300-法国-克罗地亚', '31.00')])},
    ]

    assert results == expected
