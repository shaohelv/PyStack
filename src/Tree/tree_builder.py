'''
	Builds a public tree for Leduc Hold'em or variants.
	Each node of the tree contains the following fields:
		* `node_type`: () int. an element of @{constants.node_types} (if applicable)
		* `street`: () int. the current betting round
		* `board`: (current_board_cards,) a possibly empty vector of board cards
		* `board_string`: str. a string representation of the board cards
		* `current_player`: () int. the player acting at the node
		* `bets`: (num_players,) the number of chips that each player has committed to the pot
		* `pot`: bets.min() half the pot size, equal to the smaller number in `bets`
		* `children`: [] a list of children nodes
'''
import numpy as np

from Settings.arguments import arguments
from Settings.constants import constants
from Game.card_tools import card_tools
from Game.card_to_string_conversion import card_to_string
from Tree.strategy_filling import StrategyFilling
from Game.bet_sizing import BetSizing

from helper_classes import Node

class PokerTreeBuilder():
	def __init__(self):
		pass


	def _get_children_nodes_chance_node(self, parent_node): # wtf
		''' Creates the children nodes after a chance node.
		@param: parent_node the chance node
		@return a list of children nodes
		'''
		assert(parent_node.current_player == constants.players.chance)
		if self.limit_to_street:
			return []
		next_boards = card_tools.get_boards(parent_node.street+1)
		subtree_height = -1
		children = []
		# 1.0 iterate over the next possible boards to build the corresponding subtrees
		for i in range(next_boards.shape[0]):
			next_board = next_boards[i]
			next_board_string = card_to_string.cards_to_string(next_board)
			child = Node()
			child.node_type = constants.node_types.inner_node
			child.parent = parent_node
			child.current_player = constants.players.P1
			child.street = parent_node.street + 1
			child.board = next_board
			child.board_string = next_board_string
			child.bets = parent_node.bets.copy()
			children.append(child)
		return children


	def _fill_additional_attributes(self, node):
		''' Fills in additional convenience attributes which only depend
			on existing node attributes.
		@param: node
		'''
		node.pot = node.bets.min()


	def _get_children_player_node(self, parent_node):
		''' Creates the children nodes after a player node.
		@param: parent_node the chance node
		@return a list of children nodes
		'''
		assert(parent_node.current_player != constants.players.chance)
		children = []
		# 1.0 fold action
		fold_node = Node()
		fold_node.type = constants.node_types.terminal_fold
		fold_node.terminal = True
		fold_node.current_player = 1 - parent_node.current_player
		fold_node.street = parent_node.street
		fold_node.board = parent_node.board
		fold_node.board_string = parent_node.board_string
		fold_node.bets = parent_node.bets.copy()
		children.append(fold_node)
		# 2.0 check action
		a1 = parent_node.street == 1
		a2 = parent_node.current_player == constants.players.P1
		a3 = parent_node.num_bets == 1
		a4 = constants.limit_bet_cap > 1 or constants.nl
		a5 = parent_node.street != 1 or constants.streets_count == 1
		a6 = parent_node.current_player == constants.players.P2
		a7 = parent_node.bets[0] == parent_node.bets[1]
		b1 = parent_node.street != constants.streets_count
		b2 = parent_node.bets[0] == parent_node.bets[1]
		b3 = parent_node.street == 1
		b4 = parent_node.current_player == constants.players.P2
		b5 = parent_node.street != 1
		b6 = parent_node.current_player == constants.players.P1
		b7 = parent_node.bets[0] != parent_node.bets[1]
		b8 = parent_node.bets.max() < arguments.stack
		if (a1 and a2 and a3 and a4) or (a5 and a6 and a7):
			check_node = Node()
			check_node.type = constants.node_types.check
			check_node.terminal = False
			check_node.current_player = 1 - parent_node.current_player
			check_node.street = parent_node.street
			check_node.board = parent_node.board
			check_node.board_string = parent_node.board_string
			check_node.bets = np.full_like(parent_node.bets, parent_node.bets.max())
			check_node.num_bets = parent_node.num_bets
			children.append(check_node)
		# transition check/call
		elif b1 and ( ( b2 and ((b3 and b4) or (b5 and b6)) ) or (b7 and b8) ):
			chance_node = Node()
			chance_node.node_type = constants.node_types.chance_node
			chance_node.street = parent_node.street
			chance_node.board = parent_node.board
			chance_node.board_string = parent_node.board_string
			chance_node.current_player = constants.players.chance
			chance_node.bets = np.full_like(parent_node.bets.copy(), parent_node.bets.max())
			chance_node.num_bets = 0
			children.append(chance_node)
		# 2.0 terminal call - either last street or allin
		else:
			terminal_call_node = Node()
			terminal_call_node.type = constants.node_types.terminal_call
			terminal_call_node.terminal = True
			terminal_call_node.current_player = 1 - parent_node.current_player
			terminal_call_node.street = parent_node.street
			terminal_call_node.board = parent_node.board
			terminal_call_node.board_string = parent_node.board_string
			terminal_call_node.bets = np.full_like(parent_node.bets.copy(), parent_node.bets.max())
			children.append(terminal_call_node)
		# 3.0 bet actions
		if not constants.nl:
			if parent_node.num_bets < constants.limit_bet_cap:
				child = Node()
				# child.node_type = constants.node_types.inner_node # ? prideta papildomai
				child.parent = parent_node
				child.current_player = 1 - parent_node.current_player
				child.street = parent_node.street
				child.board = parent_node.board
				child.board_string = parent_node.board_string
				child.bets = parent_node.bets.copy()
				betsize = constants.limit_bet_sizes[parent_node.street-1]
				if parent_node.current_player == constants.players.P1:
					child.bets[0] = child.bets[1] + betsize
				else:
					child.bets[1] = child.bets[0] + betsize
				child.num_bets = parent_node.num_bets + 1
				children.append(child)
		else:
			possible_bets = self.bet_sizing.get_possible_bets(parent_node) # (N,P), P=2
			if possible_bets.ndim != 0:
				assert (possible_bets.shape[1] == 2)
				for i in range(possible_bets.shape[0]):
					child = Node()
					# child.node_type = constants.node_types.inner_node # ? prideta papildomai
					child.parent = parent_node
					child.current_player = 1 - parent_node.current_player
					child.street = parent_node.street
					child.board = parent_node.board
					child.board_string = parent_node.board_string
					child.bets = possible_bets[i]
					children.append(child)
		return children


	def _get_children_nodes(self, parent_node):
		''' Creates the children after a node.
		@param: parent_node the node to create children for
		@return a list of children nodes
		'''
		chance_node = parent_node.current_player == constants.players.chance
		# transition call -> create a chance node
		if parent_node.terminal:
			return []
		# chance node
		elif chance_node:
			return self._get_children_nodes_chance_node(parent_node)
		# inner nodes -> handle bet sizes
		else:
			return self._get_children_player_node(parent_node)
		assert(False)


	def _build_tree_dfs(self, current_node):
		''' Recursively build the (sub)tree rooted at the current node.
		@param: current_node the root to build the (sub)tree from
		@return `current_node` after the (sub)tree has been built
		'''
		self._fill_additional_attributes(current_node)
		children = self._get_children_nodes(current_node)
		current_node.children = children
		depth = 0
		current_node.actions = np.zeros([len(children)], dtype=arguments.int_dtype)
		for i in range(len(children)):
			children[i].parent = current_node
			self._build_tree_dfs(children[i])
			depth = max(depth, children[i].depth)
			if i == 0:
				current_node.actions[i] = constants.actions.fold
			elif i == 1:
				current_node.actions[i] = constants.actions.ccall
			else:
				if not constants.nl:
					assert(i==2) # wtf child
					current_node.actions[i] = constants.actions.raise_
				else:
					current_node.actions[i] = children[i].bets.max()
		current_node.depth = depth + 1
		return current_node


	def build_tree(self, params):
		''' Builds the tree.
		@param: params table of tree parameters
		@return the root node of the built tree
		'''
		root = Node()
		# copy necessary stuff from the root_node not to touch the input
		root.street = params.root_node.street
		root.bets = params.root_node.bets.copy()
		root.num_bets = params.root_node.num_bets
		root.current_player = params.root_node.current_player
		root.board = params.root_node.board.copy()
		self.bet_sizing = params.bet_sizing or BetSizing(arguments.bet_sizing)
		assert(self.bet_sizing)
		self.limit_to_street = params.limit_to_street
		self._build_tree_dfs(root)
		strategy_filling = StrategyFilling()
		strategy_filling.fill_uniform(root)
		return root


tree_builder = PokerTreeBuilder()